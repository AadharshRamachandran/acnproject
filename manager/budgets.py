"""5QI-derived one-way delay budgets and their RTT equivalents."""


CLASSES = ("voip", "video", "bulk")


def class_delay_budgets_ms(config):
    """Return per-class one-way budgets: configured link share × 5QI PDB."""
    policy = config["fiveqi"]
    default_share = float(policy["link_share"])
    shares = policy.get("class_shares", {})
    pdbs = policy["pdb_ms"]
    allowed = [float(value) for value in policy.get("allowed_link_shares", ())]
    if allowed and not any(abs(default_share - value) < 1e-9 for value in allowed):
        raise ValueError(f"fiveqi.link_share must be one of {allowed}")
    for cls, share in shares.items():
        if allowed and not any(abs(float(share) - value) < 1e-9 for value in allowed):
            raise ValueError(f"fiveqi.class_shares.{cls} must be one of {allowed}")
    budgets = {
        cls: float(pdbs[cls]) * float(shares.get(cls, default_share))
        for cls in CLASSES
    }
    if any(value <= 0 for value in budgets.values()):
        raise ValueError("5QI-derived class delay budgets must be positive")
    return budgets


def class_rtt_budgets_ms(config):
    """Convert one-way link budgets to the symmetric RTT limits used by probes."""
    return {cls: 2.0 * value for cls, value in class_delay_budgets_ms(config).items()}
