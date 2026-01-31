import cv2
import numpy as np
import os
import time
import matplotlib
matplotlib.use('TkAgg') #prevents plot hangs on macOS
import matplotlib.pyplot as plt
from concurrent.futures import ProcessPoolExecutor
import bacteria_bouncer_config as config

#shared resources for parallel processing
progress_counter = None
start_time_ref = None

def init_worker(counter, t_ref, k_size, c_crop, s_buffer, s_mult):
    #initializes shared memory and syncs GUI settings to workers
    global progress_counter, start_time_ref
    progress_counter = counter
    start_time_ref = t_ref
    config.gaussian_kernel_size = k_size
    config.crop_radius_ratio = c_crop
    config.safety_buffer = s_buffer 
    config.std_dev_multiplier = s_mult

def get_high_detail_coverage(file_path):
    #loading 16-bit TIF
    img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
    if img is None: return 0.0, None

    #applying circular crop
    height, width = img.shape[:2]
    circle_mask = np.zeros((height, width), dtype=np.uint8)
    center = (int(width / 2), int(height / 2))
    radius = int(min(height, width) * config.crop_radius_ratio / 2)
    cv2.circle(circle_mask, center, radius, 255, -1)
    
    #fill outside of circle with median to avoid edge noise
    img_median = np.median(img)
    img = np.where(circle_mask == 255, img, img_median).astype(img.dtype)

    #filtering noise
    blur = cv2.GaussianBlur(img, (config.gaussian_kernel_size, config.gaussian_kernel_size), 0)
    median_val = np.median(blur)
    std_dev = np.std(blur)
    
    #dynamic thresholding logic strictly tied to std_dev
    dynamic_sensitivity = max(std_dev * config.std_dev_multiplier, config.safety_buffer)
    dynamic_thresh = median_val - dynamic_sensitivity
    mask = (blur < dynamic_thresh).astype(np.uint8) * 255

    #cleaning up small noise
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    filtered_mask = np.zeros_like(mask)
    bio_pixels = 0
    
    for i in range(1, num_labels):
        x, y, w, h, area = stats[i]
        if area < config.pixel_floor: continue
        filtered_mask[labels == i] = 255
        bio_pixels += area
            
    coverage = (bio_pixels / mask.size) * 100
    return round(coverage, 3), filtered_mask

def process_manual_well(well_id, file_list, save_masks, output_dir):
    #worker function to process specific file lists
    well_data = []
    if save_masks and output_dir:
        mask_dir = os.path.join(output_dir, f"masks_{well_id}")
        os.makedirs(mask_dir, exist_ok=True)
        
    #getting junk mask from first frame
    _, initial_junk_mask = get_high_detail_coverage(file_list[0])
    
    for idx, path in enumerate(file_list):
        raw_coverage, current_mask = get_high_detail_coverage(path)
        
        if idx == 0:
            well_data.append(0.0)
        else:
            #inversing junk mask potency with std_dev of the frame
            active_junk = cv2.bitwise_and(initial_junk_mask, current_mask)
            junk_count = np.count_nonzero(active_junk)
            
            #junk adjusted growth calculation
            actual_pixels = np.count_nonzero(current_mask) - junk_count
            adjusted_coverage = (actual_pixels / current_mask.size) * 100
            well_data.append(round(max(0, adjusted_coverage), 3))
        
        if save_masks and current_mask is not None and output_dir:
            base_name = os.path.basename(path).split('.')[0]
            cv2.imwrite(os.path.join(mask_dir, f"mask_{base_name}.png"), current_mask)
    
    with progress_counter.get_lock():
        progress_counter.value += 1
    return well_id, well_data

def run_full_analysis(experiment_data, save_masks, output_dir, update_callback, k_size, c_crop, s_buffer, s_mult):
    #runs parallel workers
    import multiprocessing
    #sync local process config
    config.gaussian_kernel_size = k_size
    config.crop_radius_ratio = c_crop
    config.safety_buffer = s_buffer
    config.std_dev_multiplier = s_mult

    tasks = []
    for strain, wells in experiment_data.items():
        for well_id, files in wells.items():
            tasks.append((f"{strain}_{well_id}", files, save_masks, output_dir))
            
    total = len(tasks)
    if total == 0: return {}, 0
    
    counter = multiprocessing.Value('i', 0)
    start_time = multiprocessing.Value('d', time.time())
    
    workers = max(1, os.cpu_count() - 1)
    with ProcessPoolExecutor(max_workers=workers, initializer=init_worker, 
                             initargs=(counter, start_time, k_size, c_crop, s_buffer, s_mult)) as executor:
        futures = [executor.submit(process_manual_well, t[0], t[1], t[2], t[3]) for t in tasks]
        while any(f.running() for f in futures):
            update_callback(counter.value, total, start_time.value)
            time.sleep(0.5)
        results = [f.result() for f in futures]

    grouped = {}
    for task_id, well_results in results:
        strain = task_id.split('_')[0]
        if strain not in grouped:
            grouped[strain] = [[] for _ in range(len(well_results))]
        for hr, val in enumerate(well_results):
            grouped[strain][hr].append(val)
            
    return grouped, int(time.time() - start_time.value)

def show_interactive_plot(strain_data):
    #generates plot
    plt.style.use('default') 
    fig, ax = plt.subplots(figsize=(9, 9))
    for s in ax.spines.values():
        s.set_linewidth(2); s.set_color('black')

    sorted_strains = sorted(strain_data.keys())
    if not sorted_strains: return
    
    #calculate normalization factor from first strain baseline
    baseline_id = sorted_strains[0]
    baseline_raw_avgs = [np.mean(h) for h in strain_data[baseline_id]]
    baseline_peak = max(baseline_raw_avgs) if baseline_raw_avgs else 0

    cmap = plt.get_cmap('tab10')
    frames = list(range(len(strain_data[baseline_id])))

    for idx, strain in enumerate(sorted_strains):
        data = strain_data[strain]
        avg = np.array([np.mean(h) for h in data])
        std = np.array([np.std(h) for h in data])
        
        #normalization safety check
        if baseline_peak > 0:
            n_avg, n_std = avg / baseline_peak, std / baseline_peak
        else:
            n_avg, n_std = avg, std
            
        color = '#333333' if idx == 0 else cmap(idx % 10)
        
        ax.fill_between(frames, n_avg - n_std, n_avg + n_std, color=color, alpha=0.15, lw=0)
        ax.plot(frames, n_avg, label=f"{strain}", color=color, linewidth=4, marker='o', markersize=8)

    ax.set_xlabel("Time (Frame)", fontsize=18); ax.set_ylabel("Biomass (a.u.)", fontsize=18)
    ax.legend(loc='upper left'); plt.tight_layout()
    
    m = plt.get_current_fig_manager()
    if hasattr(m, 'window'):
        m.window.attributes('-topmost', 1); m.window.attributes('-topmost', 0)
    plt.show()