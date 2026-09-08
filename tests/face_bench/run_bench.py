import os
import sys
import glob
import time
import argparse
import numpy as np
import cv2
from collections import defaultdict
from itertools import combinations, product

# Setup sys.path so modules can be run directly
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_engine.intelligence.face_engine import FaceEngine

def run_benchmark(dataset_dir: str):
    """
    Computes FAR/FRR/EER across a dataset of person_name/*.jpg.
    Prints a threshold sweep table to identify the optimal operating point.
    """
    print(f"=== IBVAP Face Engine Benchmark ===")
    print(f"Dataset: {dataset_dir}")
    
    if not os.path.isdir(dataset_dir):
        print(f"Error: Dataset directory {dataset_dir} does not exist.")
        return

    engine = FaceEngine()
    
    # Extract embeddings for all images
    embeddings_by_person = defaultdict(list)
    total_images = 0
    failed_images = 0
    
    print("\n[1] Extracting embeddings...")
    start_time = time.time()
    for person_name in os.listdir(dataset_dir):
        person_dir = os.path.join(dataset_dir, person_name)
        if not os.path.isdir(person_dir):
            continue
            
        for img_path in glob.glob(os.path.join(person_dir, "*.*")):
            ext = os.path.splitext(img_path)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.png']:
                continue
                
            total_images += 1
            img_bgr = cv2.imread(img_path)
            if img_bgr is None:
                failed_images += 1
                continue
                
            success, emb, _, _ = engine.process_registration_image(img_bgr)
            if success and emb is not None:
                embeddings_by_person[person_name].append(emb)
            else:
                failed_images += 1
                
    elapsed = time.time() - start_time
    print(f"Processed {total_images} images in {elapsed:.2f}s.")
    print(f"Failed to detect usable faces in {failed_images} images.")
    
    persons_count = len(embeddings_by_person)
    valid_images = sum(len(embs) for embs in embeddings_by_person.values())
    print(f"Successfully extracted {valid_images} embeddings across {persons_count} identities.")
    
    if valid_images < 2:
        print("Not enough valid images to run benchmarks.")
        return
        
    print("\n[2] Computing genuine and impostor scores...")
    genuine_scores = []
    impostor_scores = []
    
    # Genuine pairs (same person)
    for person, embs in embeddings_by_person.items():
        if len(embs) < 2:
            continue
        for emb1, emb2 in combinations(embs, 2):
            score = engine.compare_faces(emb1, emb2)
            genuine_scores.append(score)
            
    # Impostor pairs (different persons)
    persons = list(embeddings_by_person.keys())
    for i in range(len(persons)):
        for j in range(i + 1, len(persons)):
            for emb1, emb2 in product(embeddings_by_person[persons[i]], embeddings_by_person[persons[j]]):
                score = engine.compare_faces(emb1, emb2)
                impostor_scores.append(score)
                
    print(f"Computed {len(genuine_scores)} genuine pairs and {len(impostor_scores)} impostor pairs.")
    
    if not genuine_scores or not impostor_scores:
        print("Not enough pairs (need at least one person with multiple images, and multiple persons).")
        return
        
    print("\n[3] Threshold Sweep (Cosine Score)")
    print(f"{'Threshold':<10} | {'FAR (%)':<10} | {'FRR (%)':<10} | {'Sum (%)':<10}")
    print("-" * 46)
    
    thresholds = np.arange(0.20, 0.65, 0.01)
    
    best_eer_diff = float('inf')
    eer_thresh = None
    eer_val = None
    
    for t in thresholds:
        # FAR: Impostor score >= threshold
        false_accepts = sum(1 for s in impostor_scores if s >= t)
        far = (false_accepts / len(impostor_scores)) * 100
        
        # FRR: Genuine score < threshold
        false_rejects = sum(1 for s in genuine_scores if s < t)
        frr = (false_rejects / len(genuine_scores)) * 100
        
        diff = abs(far - frr)
        if diff < best_eer_diff:
            best_eer_diff = diff
            eer_thresh = t
            eer_val = (far + frr) / 2
            
        print(f"{t:.2f}       | {far:<10.2f} | {frr:<10.2f} | {far+frr:<10.2f}")
        
    print("-" * 46)
    print(f"Optimal EER (Equal Error Rate) point:")
    print(f"Threshold ≈ {eer_thresh:.2f} (EER ≈ {eer_val:.2f}%)")
    print("\nRecommend setting MATCH_THRESHOLD_STRICT based on acceptable FAR tolerance.")
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to dataset directory (structure: name/img1.jpg, name/img2.jpg)")
    args = parser.parse_args()
    run_benchmark(args.dataset)
