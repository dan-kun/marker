"""Short, distinguishable labels for paths that may share a file name."""

import os


def display(path: str) -> str:
    """path as text that can always be shown. Python keeps bytes of a file
    name that are not valid UTF-8 as lone surrogates, which GTK refuses."""
    try:
        path.encode("utf-8")
        return path
    except UnicodeEncodeError:
        return path.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def short_labels(paths: list[str]) -> dict[str, str]:
    """Map each path to its file name, adding just enough of the parent
    folders to tell apart paths that share a name:

        /work/README.md, /home/notes/README.md → "README.md — work", "README.md — notes"
        /a/docs/x.md, /b/docs/x.md             → "x.md — a/docs", "x.md — b/docs"
    """
    labels = {path: display(os.path.basename(path.rstrip(os.sep)) or path) for path in paths}
    groups: dict[str, list[str]] = {}
    for path in dict.fromkeys(paths):  # unique, in order
        groups.setdefault(labels[path], []).append(path)

    for name, group in groups.items():
        if len(group) < 2:
            continue
        parents = {
            path: [part for part in os.path.dirname(path.rstrip(os.sep)).split(os.sep) if part]
            for path in group
        }
        depth = 1
        longest = max(len(parts) for parts in parents.values())
        while depth < longest and len({tuple(parts[-depth:]) for parts in parents.values()}) < len(group):
            depth += 1
        for path in group:
            suffix = display("/".join(parents[path][-depth:]))
            labels[path] = f"{name} — {suffix}" if suffix else name
    return labels
