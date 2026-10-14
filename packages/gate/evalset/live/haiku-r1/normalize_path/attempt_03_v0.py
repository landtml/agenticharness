def normalize_path(p: str) -> str:
    absolute = p.startswith('/')
    parts = []
    for comp in p.split('/'):
        if comp == '' or comp == '.':
            continue
        if comp == '..':
            if parts and parts[-1] != '..':
                parts.pop()
            elif not absolute:
                parts.append('..')
        else:
            parts.append(comp)
    body = '/'.join(parts)
    if absolute:
        return '/' + body
    return body or '.'
