"""
AutoPlanetaryMagnetosphere baseline experiment.

This is a deterministic, dependency-free surrogate benchmark for induced
magnetosphere responses around Mars-like and Venus-like terrestrial planets.
It is designed as an Vegapunk discovery task input, not as a validated
planetary plasma simulation.
"""

import json
import math
import os
import random
import time


FEATURE_NAMES = [
    "planet_venus_flag",
    "solar_wind_speed_kms",
    "proton_density_cm3",
    "dynamic_pressure_npa",
    "imf_bx_nt",
    "imf_by_nt",
    "imf_bz_nt",
    "imf_strength_nt",
    "clock_angle_sin",
    "clock_angle_cos",
    "f107_proxy",
    "solar_cycle_sin",
    "solar_cycle_cos",
    "convective_e_mvm",
    "ion_gyroradius_proxy",
    "pickup_source_proxy",
]

TARGET_NAMES = [
    "bow_shock_standoff_rp",
    "magnetic_pileup_boundary_rp",
    "ion_escape_log10_s",
    "acceleration_index",
]


def _uniform(rng, low, high):
    return low + (high - low) * rng.random()


def generate_sample(rng):
    planet_venus = 1.0 if rng.random() < 0.5 else 0.0

    speed = _uniform(rng, 300.0, 820.0)
    density = 10.0 ** _uniform(rng, math.log10(1.0), math.log10(35.0))
    dynamic_pressure = 1.6726e-6 * density * speed * speed

    imf_strength = _uniform(rng, 1.0, 25.0)
    clock_angle = _uniform(rng, -math.pi, math.pi)
    cone_angle = _uniform(rng, -0.85, 0.85)
    bx = imf_strength * cone_angle
    transverse = imf_strength * math.sqrt(max(0.0, 1.0 - cone_angle * cone_angle))
    by = transverse * math.sin(clock_angle)
    bz = transverse * math.cos(clock_angle)

    solar_phase = _uniform(rng, 0.0, 2.0 * math.pi)
    f107 = 105.0 + 62.0 * math.sin(solar_phase) + _uniform(rng, -18.0, 18.0)
    f107 = min(240.0, max(60.0, f107))
    euv_norm = (f107 - 60.0) / 180.0

    convective_e = speed * abs(by) * 1.0e-3
    ion_gyroradius = speed / max(imf_strength, 0.5)
    pickup_source = (0.78 + 0.34 * planet_venus) * (0.35 + euv_norm) * math.sqrt(density)

    pressure_term = math.log1p(dynamic_pressure)
    imf_southward = max(0.0, -bz) / imf_strength
    draping_shear = abs(by) / imf_strength
    cycle_compression = 0.5 + 0.5 * math.cos(solar_phase - 0.7)

    bow_shock = (
        1.74
        - 0.11 * planet_venus
        - 0.155 * pressure_term
        + 0.105 * euv_norm
        + 0.052 * draping_shear
        + 0.032 * math.sin(clock_angle + 0.6 * planet_venus)
        - 0.018 * imf_southward * pressure_term
        + _uniform(rng, -0.018, 0.018)
    )

    pileup_gap = (
        0.275
        + 0.035 * planet_venus
        + 0.030 * math.tanh(pressure_term - 1.0)
        - 0.025 * euv_norm
        + 0.020 * imf_southward
    )
    magnetic_pileup = bow_shock - pileup_gap + _uniform(rng, -0.012, 0.012)

    escape_log = (
        23.72
        + 0.23 * pressure_term
        + 0.42 * euv_norm
        + 0.13 * planet_venus
        + 0.18 * math.log1p(convective_e)
        + 0.09 * imf_southward * cycle_compression
        + 0.06 * math.sin(clock_angle) * (0.4 + euv_norm)
        + _uniform(rng, -0.030, 0.030)
    )

    acceleration = (
        0.86
        + 0.18 * pressure_term
        + 0.26 * math.log1p(convective_e)
        + 0.10 * imf_southward
        + 0.055 * math.sqrt(ion_gyroradius)
        + 0.045 * planet_venus * euv_norm
        + _uniform(rng, -0.020, 0.020)
    )

    features = [
        planet_venus,
        speed,
        density,
        dynamic_pressure,
        bx,
        by,
        bz,
        imf_strength,
        math.sin(clock_angle),
        math.cos(clock_angle),
        f107,
        math.sin(solar_phase),
        math.cos(solar_phase),
        convective_e,
        ion_gyroradius,
        pickup_source,
    ]
    targets = [bow_shock, magnetic_pileup, escape_log, acceleration]
    return features, targets


def generate_dataset(n_samples=960, seed=20260708):
    rng = random.Random(seed)
    features = []
    targets = []
    for _ in range(n_samples):
        x, y = generate_sample(rng)
        features.append(x)
        targets.append(y)
    return features, targets


def train_test_split(features, targets, test_ratio=0.2, seed=42):
    indices = list(range(len(features)))
    rng = random.Random(seed)
    rng.shuffle(indices)
    split = int(len(indices) * (1.0 - test_ratio))
    train_idx = indices[:split]
    test_idx = indices[split:]
    return (
        [features[i] for i in train_idx],
        [features[i] for i in test_idx],
        [targets[i] for i in train_idx],
        [targets[i] for i in test_idx],
    )


def fit_standardizer(rows):
    cols = len(rows[0])
    means = [sum(row[j] for row in rows) / len(rows) for j in range(cols)]
    stds = []
    for j in range(cols):
        var = sum((row[j] - means[j]) ** 2 for row in rows) / max(1, len(rows) - 1)
        stds.append(math.sqrt(var) if var > 1.0e-12 else 1.0)
    return means, stds


def transform(rows, means, stds):
    return [[(row[j] - means[j]) / stds[j] for j in range(len(row))] for row in rows]


def add_intercept(rows):
    return [[1.0] + row for row in rows]


def solve_linear_system(matrix, vector):
    n = len(matrix)
    a = [row[:] + [vector[i]] for i, row in enumerate(matrix)]

    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1.0e-12:
            raise ValueError("Singular matrix in ridge solve")
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]

        pivot_value = a[col][col]
        for k in range(col, n + 1):
            a[col][k] /= pivot_value

        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if factor == 0.0:
                continue
            for k in range(col, n + 1):
                a[row][k] -= factor * a[col][k]

    return [a[i][n] for i in range(n)]


def fit_ridge_regression(features, targets, ridge=0.35):
    x = add_intercept(features)
    n_features = len(x[0])
    n_targets = len(targets[0])

    xtx = [[0.0 for _ in range(n_features)] for _ in range(n_features)]
    xty = [[0.0 for _ in range(n_targets)] for _ in range(n_features)]

    for row, target in zip(x, targets):
        for i in range(n_features):
            for j in range(n_features):
                xtx[i][j] += row[i] * row[j]
            for t in range(n_targets):
                xty[i][t] += row[i] * target[t]

    for i in range(1, n_features):
        xtx[i][i] += ridge

    weights_by_target = []
    for t in range(n_targets):
        weights_by_target.append(solve_linear_system(xtx, [xty[i][t] for i in range(n_features)]))

    return weights_by_target


def predict(features, weights_by_target):
    x = add_intercept(features)
    predictions = []
    for row in x:
        pred = []
        for weights in weights_by_target:
            pred.append(sum(value * weight for value, weight in zip(row, weights)))
        predictions.append(pred)
    return predictions


def mean_absolute_error(actual, predicted, target_index):
    return sum(abs(a[target_index] - p[target_index]) for a, p in zip(actual, predicted)) / len(actual)


def root_mean_squared_error(actual, predicted, target_index):
    mse = sum((a[target_index] - p[target_index]) ** 2 for a, p in zip(actual, predicted)) / len(actual)
    return math.sqrt(mse)


def r2_score(actual, predicted, target_index):
    values = [row[target_index] for row in actual]
    mean_value = sum(values) / len(values)
    ss_tot = sum((value - mean_value) ** 2 for value in values)
    ss_res = sum((a[target_index] - p[target_index]) ** 2 for a, p in zip(actual, predicted))
    if ss_tot <= 1.0e-12:
        return 0.0
    return 1.0 - ss_res / ss_tot


def evaluate(actual, predicted):
    bow_mae = mean_absolute_error(actual, predicted, 0)
    pileup_mae = mean_absolute_error(actual, predicted, 1)
    boundary_location_mae = 0.5 * (bow_mae + pileup_mae)
    escape_log_mae = mean_absolute_error(actual, predicted, 2)
    acceleration_rmse = root_mean_squared_error(actual, predicted, 3)
    r2_values = [r2_score(actual, predicted, i) for i in range(len(TARGET_NAMES))]
    mean_r2 = sum(r2_values) / len(r2_values)

    combined_score = (
        boundary_location_mae
        + 0.45 * escape_log_mae
        + 0.35 * acceleration_rmse
        + 0.10 * max(0.0, 1.0 - mean_r2)
    )

    return {
        "combined_score": combined_score,
        "boundary_location_mae": boundary_location_mae,
        "bow_shock_mae": bow_mae,
        "magnetic_pileup_mae": pileup_mae,
        "escape_log_mae": escape_log_mae,
        "acceleration_rmse": acceleration_rmse,
        "mean_r2": mean_r2,
        "target_r2": {name: r2_values[i] for i, name in enumerate(TARGET_NAMES)},
    }


def run_experiment(config=None):
    if config is None:
        config = {}

    seed = config.get("seed", 20260708)
    n_samples = config.get("n_samples", 960)
    test_ratio = config.get("test_ratio", 0.2)
    ridge = config.get("ridge", 0.35)

    start_time = time.time()
    features, targets = generate_dataset(n_samples=n_samples, seed=seed)
    x_train, x_test, y_train, y_test = train_test_split(features, targets, test_ratio=test_ratio)

    x_mean, x_std = fit_standardizer(x_train)
    y_mean, y_std = fit_standardizer(y_train)
    x_train_scaled = transform(x_train, x_mean, x_std)
    x_test_scaled = transform(x_test, x_mean, x_std)
    y_train_scaled = transform(y_train, y_mean, y_std)

    weights = fit_ridge_regression(x_train_scaled, y_train_scaled, ridge=ridge)
    pred_scaled = predict(x_test_scaled, weights)
    predictions = []
    for row in pred_scaled:
        predictions.append([row[j] * y_std[j] + y_mean[j] for j in range(len(TARGET_NAMES))])

    metrics = evaluate(y_test, predictions)
    runtime = time.time() - start_time

    return {
        "metrics": metrics,
        "training_time": runtime,
        "config": {
            "seed": seed,
            "n_samples": n_samples,
            "test_ratio": test_ratio,
            "ridge": ridge,
            "features": FEATURE_NAMES,
            "targets": TARGET_NAMES,
        },
    }


def main():
    results = run_experiment()
    output = {
        "combined_score": results["metrics"]["combined_score"],
        "boundary_location_mae": results["metrics"]["boundary_location_mae"],
        "escape_log_mae": results["metrics"]["escape_log_mae"],
        "acceleration_rmse": results["metrics"]["acceleration_rmse"],
        "mean_r2": results["metrics"]["mean_r2"],
        "target_r2": results["metrics"]["target_r2"],
        "training_time": results["training_time"],
        "config": results["config"],
    }

    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    output_path = os.path.join(parent_dir, "final_info.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print("AutoPlanetaryMagnetosphere baseline")
    print(f"combined_score: {output['combined_score']:.6f}")
    print(f"boundary_location_mae: {output['boundary_location_mae']:.6f}")
    print(f"escape_log_mae: {output['escape_log_mae']:.6f}")
    print(f"acceleration_rmse: {output['acceleration_rmse']:.6f}")
    print(f"mean_r2: {output['mean_r2']:.6f}")
    print(f"Results saved to: {output_path}")
    return output


if __name__ == "__main__":
    main()
