import base64
import radar_db as R

class Resp:
  def __init__(self, code, js=None, content=b""):
    self.status_code, self._js, self.content = code, js or {}, content
  def json(self): return self._js


class FakeGH:
  """Çok küçük bir GitHub API taklidi (çoklu dosya destekli)."""
  def __init__(self, branch=False, data=None, repo_ok=True):
    self.branch, self.data, self.repo_ok = branch, data, repo_ok
    self.sha_n = 0; self.calls = []; self.sha = None; self.conflict_once = False
    self.files = {}
    if data is not None:
      self._bump()
      self.files["db/radar.db"] = (data, self.sha)
  def _bump(self): self.sha_n += 1; self.sha = f"sha{self.sha_n}"
  def request(self, method, url, headers=None, timeout=None, params=None, json=None, **kw):
    path = url.replace(R.GITHUB_API, ""); self.calls.append((method, path))
    assert "Bearer" in headers["Authorization"]
    if method == "GET" and path.count("/") == 3:
      return Resp(200 if self.repo_ok else 404)
    if method == "GET" and "/contents/" in path:
      sub = path.split("/contents/", 1)[1].split("?")[0]
      f_entry = self.files.get(sub)
      if f_entry is None and sub == "db/radar.db" and self.data is not None:
        f_entry = (self.data, self.sha)
      if f_entry is None: return Resp(404)
      c_data, c_sha = f_entry
      if "raw" in headers.get("Accept", ""): return Resp(200, content=c_data)
      return Resp(200, {"encoding": "base64", "content": base64.b64encode(c_data).decode(), "sha": c_sha})
    if method == "GET" and "/git/ref/" in path:
      return Resp(200 if self.branch else 404)
    if method == "PUT":
      if self.conflict_once:
        self.conflict_once = False; self._bump(); return Resp(409)
      sub = path.split("/contents/", 1)[1].split("?")[0]
      old_entry = self.files.get(sub)
      if old_entry and json.get("sha") and json.get("sha") != old_entry[1]:
        return Resp(409)
      content = base64.b64decode(json["content"])
      self._bump()
      self.files[sub] = (content, self.sha)
      if sub == "db/radar.db" or self.data is None:
        self.data = content
      self.branch = True
      return Resp(200, {"content": {"sha": self.sha}})
    if method == "POST" and path.endswith("/blobs"):
      raw = base64.b64decode(json["content"])
      self.blobs = getattr(self, "blobs", []) + [raw]
      self.blob_by_sha = getattr(self, "blob_by_sha", {})
      b_sha = f"blob{len(self.blobs)}"
      self.blob_by_sha[b_sha] = raw
      if raw.startswith(R.SQLITE_MAGIC): self._blob = raw
      return Resp(201, {"sha": b_sha})
    if method == "POST" and path.endswith("/trees"):
      self.tree = json["tree"]; return Resp(201, {"sha": "tree1"})
    if method == "POST" and path.endswith("/commits"):
      assert json["parents"] == []; return Resp(201, {"sha": "commit1"})
    if method == "POST" and path.endswith("/refs"):
      self.branch = True; self.data = self._blob; self._bump()
      if self.data: self.files["db/radar.db"] = (self.data, self.sha)
      if hasattr(self, "tree"):
        for e in self.tree:
          raw_c = getattr(self, "blob_by_sha", {}).get(e["sha"], b"")
          self.files[e["path"]] = (raw_c, e["sha"])
      return Resp(201)
    return Resp(500)


