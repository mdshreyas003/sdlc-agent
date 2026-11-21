// Repo tree from a flat list of file paths, and file URL helpers.
export const decodeSeg = (s: string) => { try { return decodeURIComponent(s); } catch { return s; } };
export const fileHref = (base: string, path: string) => `${base}/f/${path.split("/").map(encodeURIComponent).join("/")}`;

export interface TreeNode { name: string; path: string; dir: boolean; children: TreeNode[] }

export const buildTree = (paths: string[]): TreeNode[] => {
  const root: TreeNode = { name: "", path: "", dir: true, children: [] };
  for (const p of [...new Set(paths)].sort()) {
    let cur = root;
    p.split("/").forEach((name, i, a) => {
      const path = a.slice(0, i + 1).join("/");
      let child = cur.children.find((c) => c.path === path);
      if (!child) { child = { name, path, dir: i < a.length - 1, children: [] }; cur.children.push(child); }
      cur = child;
    });
  }
  const sort = (t: TreeNode) => { t.children.sort((a, b) => Number(b.dir) - Number(a.dir) || a.name.localeCompare(b.name)); t.children.forEach(sort); };
  sort(root);
  // Collapse single-child folder chains ("clients/src/main/java" is one row), as editors do: deep trees stay shallow.
  const compact = (t: TreeNode) => {
    t.children.forEach(compact);
    while (t.dir && t.path && t.children.length === 1 && t.children[0].dir) {
      const only = t.children[0];
      t.name = `${t.name}/${only.name}`; t.path = only.path; t.children = only.children;
    }
  };
  root.children.forEach(compact);
  return root.children;
};

/** Fit a name into `max` characters: files keep their extension, folder chains keep their last segments. */
export const shortName = (name: string, dir: boolean, max = 30) => {
  if (name.length <= max) return name;
  if (dir) return `…${name.slice(-(max - 1))}`;
  const ext = /\.[^./]{1,8}$/.exec(name)?.[0] ?? "";
  return `${name.slice(0, max - ext.length - 1)}…${ext}`;
};
