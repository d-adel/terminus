def _label(obj: dict) -> str:
    return f"{obj['name']}@{obj['version']}"


def _measured(measurement: dict) -> str:
    return f"{measurement['value']:.6g} ± {measurement['uncertainty']:.2g} {measurement['unit']}"


def render(store, determination_digest: str, indent: str = "") -> str:
    determination = store.get(determination_digest)
    claim = store.get(determination["claim"])
    lines = []
    if not indent:
        scheme = store.get(claim["scheme"])
        artifact = store.get(claim["artifact"])
        lines += [
            f"{determination['status']}  {scheme['publisher']}/{_label(scheme)}  requirement {claim['requirement']}",
            f"artifact {artifact['name']} {artifact['repo']}@{artifact['commit']}",
            f"established {len(determination['established_scope'])} of {len(determination['requested_scope'])} cases",
        ]
    for reason in determination["reasons"]:
        if "claim" in reason:
            child_claim = store.get(store.get(reason["claim"])["claim"])
            lines.append(f"{indent}  {child_claim['requirement']}: {reason['finding']}")
            lines.append(render(store, reason["claim"], indent + "    "))
        else:
            lines.append(f"{indent}  {_label(store.get(reason['case']))}: {reason['finding']}")
    for note in determination["notes"]:
        lines.append(f"{indent}  note: {note}")
    if not indent:
        lines.append(f"determination {determination_digest}")
    return "\n".join(line for line in lines if line)


def to_gsn(store, determination_digest: str, prefix: str = "") -> dict:
    determination = store.get(determination_digest)
    claim = store.get(determination["claim"])
    scheme = store.get(claim["scheme"])
    artifact = store.get(claim["artifact"])
    goal = f"{prefix}G1"
    doc = {goal: {"text": f"{artifact['name']} meets {_label(scheme)} {claim['requirement']} [{determination['status']}]"}}
    supported = []
    for index, digest in enumerate(determination["arguments"], 1):
        argument = store.get(digest)
        if argument["pattern"] == "all_of" and argument["role"] == "supports":
            strategy = f"{prefix}S{index}"
            doc[strategy] = {"text": "Every child claim holds", "supportedBy": []}
            supported.append(strategy)
            for number, premise in enumerate(argument["premises"], 1):
                child = f"{prefix}C{number}_"
                doc.update(to_gsn(store, premise, child))
                doc[strategy]["supportedBy"].append(f"{child}G1")
        elif argument["pattern"] == "all_of":
            child = f"{prefix}F{index}_"
            doc.update(to_gsn(store, argument["witness"], child))
            doc[f"{prefix}CSn{index}"] = {"text": f"A child claim failed: {child}G1", "challenges": goal}
        elif argument["role"] == "supports":
            strategy = f"{prefix}S{index}"
            doc[strategy] = {"text": f"All {len(determination['requested_scope'])} listed cases conform", "supportedBy": []}
            supported.append(strategy)
            for number, premise in enumerate(argument["premises"], 1):
                measurement = store.get(premise)
                solution = f"{prefix}Sn{index}_{number}"
                doc[solution] = {"text": f"{_label(store.get(measurement['case']))}: {_measured(measurement)}"}
                doc[strategy]["supportedBy"].append(solution)
        else:
            measurement = store.get(argument["premises"][0])
            doc[f"{prefix}CSn{index}"] = {
                "text": f"Counterexample {_label(store.get(argument['witness']))}: {_measured(measurement)}",
                "challenges": goal,
            }
    if supported:
        doc[goal]["supportedBy"] = supported
    else:
        doc[goal]["undeveloped"] = True
    return doc
