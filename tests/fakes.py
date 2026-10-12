import base64
import radar_db as R

class Resp:
  def __init__(self, code, js=None, content=b""):
    self.status_code, self._js, self.content = code, js or {}, content
  def json(self): return self._js


class FakeGH:
  """Çok küçük bir GitHub API taklidi."""
  def __init__(self, branch=False, data=None, repo_ok=True):
    self.branch, self.data, self.repo_ok = branch, data, repo_ok
    self.sha_n = 0; self.calls = []; self.sha = None; self.conflict_once = False
    if data is not None: self._bump()
  def _bump(self): self.sha_n += 1; self.sha = f"sha{self.sha_n}"
  def request(self, method, url, headers=None, timeout=None, params=None, json=None, **kw):
    path = url.replace(R.GITHUB_API, ""); self.calls.append((method, path))
    assert "Bearer" in headers["Authorization"]
    if method == "GET" and path.count("/") == 3:
      return Resp(200 if self.repo_ok else 404)
    if method == "GET" and "/contents/" in path:
      if self.data is None: return Resp(404)
      if "raw" in headers["Accept"]: return Resp(200, content=self.data)
      return Resp(200, {"encoding": "base64", "content": base64.b64encode(self.data).decode(), "sha": self.sha})
    if method == "GET" and "/git/ref/" in path:
      return Resp(200 if self.branch else 404)
    if method == "PUT":
      if self.conflict_once:
        self.conflict_once = False; self._bump(); return Resp(409)
      if self.data is not None and json.get("sha") != self.sha: return Resp(409)
      self.data = base64.b64decode(json["content"]); self._bump(); self.branch = True
      return Resp(200, {"content": {"sha": self.sha}})
    if method == "POST" and path.endswith("/blobs"):
      raw = base64.b64decode(json["content"]); self.blobs = getattr(self, "blobs", []) + [raw]
      if raw.startswith(R.SQLITE_MAGIC): self._blob = raw
      return Resp(201, {"sha": f"blob{len(self.blobs)}"})
    if method == "POST" and path.endswith("/trees"):
      self.tree = json["tree"]; return Resp(201, {"sha": "tree1"})
    if method == "POST" and path.endswith("/commits"):
      assert json["parents"] == []; return Resp(201, {"sha": "commit1"})
    if method == "POST" and path.endswith("/refs"):
      self.branch = True; self.data = self._blob; self._bump(); return Resp(201)
    return Resp(500)


