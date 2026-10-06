"""Fitted-remainder removal: a secondary replay from recorded runs only.

Fit send-to-receipt latency with a token-independent intercept and nonnegative
slopes for uncached input tokens and, for text-generating models, output tokens.
The low-quantile intercept can mix network delay, fixed server time and model
misspecification; it does not identify network delay or guarantee an upper bound.
A moving-block bootstrap within each scenario gives the estimator's range.
"""

from __future__ import annotations

import numpy as np

from streamdecisionbench.lite.retry_scoring import normalized_episode_scores, summarize_normalized

METHOD = "lower_envelope_network_removed_v1"
TAU, BLOCK, RESAMPLES, SEED = 0.10, 10, 500, 0


def _received_s(record: dict) -> float:
    attempt = record["attempts"][-1]
    return attempt.get("received_s", attempt["completed_s"]) - attempt["started_s"]


def _bound(x: np.ndarray, dx: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dx < 0, -x / dx, 1e20)


def _lstsq(M: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Least squares that fails fast on a non-finite system instead of letting LAPACK print an
    error; the result is the same as before, since _solve then refits with jitter."""
    if not (np.all(np.isfinite(M)) and np.all(np.isfinite(v))):
        raise np.linalg.LinAlgError("non-finite least-squares system")
    return np.linalg.lstsq(M, v, rcond=None)[0]


def _frisch_newton(X: np.ndarray, y: np.ndarray, tau: float, beta: float = 0.99995,
                   eps: float = 1e-8, maxit: int = 500) -> np.ndarray:
    """Quantile regression by Koenker's Frisch-Newton interior point (quantreg::rq.fit.fnb)."""
    n = len(y)
    A, c, b = X.T, -y, (1 - tau) * X.sum(0)
    u, x = np.ones(n), (1 - tau) * np.ones(n)
    s = u - x
    yd = _lstsq(A.T, c)
    r = c - A.T @ yd
    r = r + 0.001 * (r == 0)
    z = np.where(r > 0, r, 0.0)
    w = z - r
    gap, it = c @ x - yd @ b + w @ u, 0
    while gap > eps and it < maxit:
        it += 1
        q = 1 / (z / x + w / s)
        r = z - w
        Q = np.sqrt(q)
        AQ, rhs = A * Q, Q * r
        dy = _lstsq(AQ.T, rhs)
        dx = q * (A.T @ dy - r)
        ds, dz = -dx, -z * (dx / x + 1)
        dw = -w * (ds / s + 1)
        fp = min(beta * min(_bound(x, dx).min(), _bound(s, ds).min()), 1.0)
        fd = min(beta * min(_bound(w, dw).min(), _bound(z, dz).min()), 1.0)
        if min(fp, fd) < 1:
            mu = z @ x + w @ s
            g = (z + fd * dz) @ (x + fp * dx) + (w + fd * dw) @ (s + fp * ds)
            mu = mu * (g / mu) ** 3 / (2 * n)
            dxdz, dsdw = dx * dz, ds * dw
            xinv, sinv = 1 / x, 1 / s
            xi = mu * (xinv - sinv)
            rhs = rhs + Q * (dxdz - dsdw - xi)
            dy = _lstsq(AQ.T, rhs)
            dx = q * (A.T @ dy + xi - r - dxdz + dsdw)
            ds = -dx
            dz = mu * xinv - z - xinv * z * dx - dxdz
            dw = mu * sinv - w - sinv * w * ds - dsdw
            fp = min(beta * min(_bound(x, dx).min(), _bound(s, ds).min()), 1.0)
            fd = min(beta * min(_bound(w, dw).min(), _bound(z, dz).min()), 1.0)
        x, s, yd = x + fp * dx, s + fp * ds, yd + fd * dy
        w, z = w + fd * dw, z + fd * dz
        gap = c @ x - yd @ b + w @ u
    return -yd


def _solve(X: np.ndarray, y: np.ndarray, tau: float) -> np.ndarray:
    """Frisch-Newton fit; only if it fails numerically (nearly collinear columns, e.g. an
    almost constant output length), refit with a tiny fixed-seed jitter on the response."""
    for attempt in range(5):
        target = y if attempt == 0 else y + np.random.default_rng(attempt).normal(0, 1e-7, len(y))
        try:
            with np.errstate(all="ignore"):
                coef = _frisch_newton(X, target, tau)
            if np.all(np.isfinite(coef)):
                return coef
        except np.linalg.LinAlgError:
            pass
    raise RuntimeError("quantile regression failed")


def fit(X: np.ndarray, y: np.ndarray, tau: float = TAU) -> np.ndarray:
    """Low-quantile fit; a token slope estimated below zero is dropped and the rest refitted."""
    columns = list(range(X.shape[1]))
    while True:
        scale = np.abs(X[:, columns]).max(0)
        scale[scale == 0] = 1
        coef = _solve(X[:, columns] / scale, y, tau) / scale
        full = np.zeros(X.shape[1])
        full[columns] = coef
        negative = [c for c in columns[1:] if full[c] < 0]
        if not negative:
            return full
        columns = [c for c in columns if c not in negative]


def _scores(episodes: list[dict], responses: dict, releases: dict, network_s: float) -> dict:
    per = [normalized_episode_scores(e, responses[e["episode_id"]], releases[e["episode_id"]], network_s=network_s)
           for e in episodes]
    summary = summarize_normalized(per)
    return {"overall": {k: summary["overall"][k] for k in ("time_accuracy", "segment_time_accuracy")},
            "by_family": {f: {k: row[k] for k in ("time_accuracy", "segment_time_accuracy")}
                          for f, row in summary["by_family"].items()},
            "clamped_requests": sum(p["normalization"].get("network_clamped_requests", 0) for p in per)}


def network_adjustment(episodes: list[dict], responses: dict, releases: dict, *, generates_text: bool,
                       resamples: int = RESAMPLES, seed: int = SEED) -> dict:
    """Estimate the per-run network delay and replay every response without it."""
    rows = [(e["episode_id"], r) for e in episodes
            for r in sorted(responses[e["episode_id"]], key=lambda r: r["t"])]
    y = np.array([_received_s(r) for _, r in rows])
    usage = [r.get("usage") or {} for _, r in rows]
    columns = [np.ones(len(rows)),
               np.array([(u.get("input_tokens", 0) - (u.get("cached_tokens") or 0)) / 1000 for u in usage], float)]
    if generates_text:
        columns.append(np.array([u.get("output_tokens", 0) for u in usage], float))
    X = np.column_stack(columns)
    coef = fit(X, y)
    rng = np.random.default_rng(seed)
    groups = [np.array([i for i, (eid, _) in enumerate(rows) if eid == e["episode_id"]]) for e in episodes]
    draws = []
    for _ in range(resamples):
        index = np.concatenate([group[(start + np.arange(min(BLOCK, len(group)))) % len(group)]
                                for group in groups
                                for start in rng.integers(0, len(group), max(1, len(group) // BLOCK))])
        draws.append(fit(X[index], y[index])[0])
    raw_low, raw_high = (float(v) for v in np.percentile(draws, [2.5, 97.5]))
    raw_estimate = float(coef[0])
    # Token slopes are nonnegative, but the fitted intercept can be negative:
    # it extrapolates to zero tokens, outside the observed input lengths. A
    # negative intercept is not a removable delay. Preserve the fit for
    # diagnosis and project only the replay offsets onto their physical domain.
    estimate, low, high = (max(0.0, value) for value in (raw_estimate, raw_low, raw_high))
    untimed = summarize_normalized([normalized_episode_scores(e, responses[e["episode_id"]], releases[e["episode_id"]])
                                    for e in episodes])
    observed = {"overall": untimed["overall"]["time_accuracy"],
                "by_family": {f: row["time_accuracy"] for f, row in untimed["by_family"].items()}}
    return {
        "method": METHOD,
        "assumption": "send-to-receipt latency is approximated by a token-independent intercept plus "
                      "nonnegative slopes for uncached input tokens and, for text-generating models, output "
                      "tokens; the fitted lower-quantile intercept is removed only in a secondary replay",
        "estimator": f"{TAU:.2f}-quantile regression intercept with nonnegative token slopes; 95% range from "
                     f"{resamples} moving-block bootstrap resamples ({BLOCK} consecutive releases within each scenario, seed {seed})",
        "network_s": {"estimate": estimate, "low": low, "high": high},
        "unconstrained_intercept_s": {"estimate": raw_estimate, "low": raw_low, "high": raw_high},
        "negative_intercept_projected": min(raw_estimate, raw_low, raw_high) < 0,
        "prefill_s_per_1k_input_tokens": float(coef[1]),
        "decode_s_per_output_token": float(coef[2]) if generates_text else None,
        "latency_floor_s": float(y.min()),
        "scores": {name: _scores(episodes, responses, releases, value)
                   for name, value in (("estimate", estimate), ("low", low), ("high", high))},
        "observed": observed,
        "untimed_ceiling": {"overall": untimed["overall"]["untimed_decision_accuracy"],
                            "by_family": {f: row["untimed_decision_accuracy"] for f, row in untimed["by_family"].items()}},
        "interpretation": "Secondary sensitivity analysis. The fitted remainder can include network delay, fixed "
                          "server time and model misspecification; it does not identify network delay or guarantee "
                          "an upper bound on its effect. Negative fitted "
                          "intercepts are retained as diagnostics and projected to zero removable delay for replay. "
                          "The range reflects estimator uncertainty only. The observed in-force score remains primary.",
    }
