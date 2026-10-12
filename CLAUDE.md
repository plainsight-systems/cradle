# Working on Cradle

Andrew writes the lesson code; Codex reviews it. Do not implement or rewrite lesson code unless Andrew asks.
Develop the articles together in Andrew's voice. Every lesson extends the same executable, with GPU use from
lesson 1.

If `CLAUDE.local.md` exists, read it for local working context. That file is ignored by Git and must not be
committed. Keep machine-specific paths and private editorial material out of tracked files.

The site and publishing pipeline are implemented; the baseline builds and runs, and the prologue is published. Numbered lesson code remains unwritten. See [README.md](README.md) for the layout. The local
`experiments/` directory is ignored; its programs are feasibility references, not the lesson implementation.
