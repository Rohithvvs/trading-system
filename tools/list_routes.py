from backend.app.main import app
paths = []
for r in getattr(app.router, 'routes', []):
    p = getattr(r, 'path', None)
    if p:
        paths.append(p)
print(paths)
