# Build and publishing commands

## .NET build and validation

Install .NET SDK **10.0.401**, Git, and Python **3.11+**. From the repository root:

```sh
python3 scripts/setup.py
dotnet build Cradle.slnx -c Release --no-restore
dotnet test Cradle.slnx -c Release --no-build --no-restore
dotnet run --project src/Cradle -c Release --no-build --no-restore
```

Use `python` on Windows if that is the installed command. Put the pinned SDK on PATH; `global.json` rejects
other SDK versions. Setup validates and builds ILGPU from the revision in `eng/ILGPU.props`, beneath ignored
`.deps/`. It checks for tracked changes or unexpected untracked files and never resets an existing checkout.
It restores the upstream compiler and solution using committed package locks and nuget.org, then runs
`check_kernel_setup.py`. That check copies the application's project settings into a temporary directory
whose path contains spaces, compiles a small kernel, explicitly executes it on the CPU, and checks all 1,031
outputs. It checks both the first and a repeated build, and verifies that the generated kernel type is
actually present in the application assembly. It neither changes the application nor requires a GPU.
The xUnit tests check runtime loading and agreement between the generated kernels and the backend
recorded for device selection. The application requires a matching GPU and verifies its numerical output.

`Cradle.csproj` imports the kernel build targets and points to the compiler built by setup. `ILGPUBackend`
defaults to `Metal` on macOS and `CUDA` elsewhere. Override it with `-p:ILGPUBackend=OpenCL` or
`-p:ILGPUBackend=ROCm` when building for those backends. Use the same setting on later rebuilds. The pin
requires one backend per build; generating several together produces invalid C#. Device selection at
runtime uses that same setting, embedded as `AssemblyMetadata` in the application. It filters out other
backends and OpenCL CPU devices before selecting a GPU by memory size. A missing matching GPU is an
error, never a CPU fallback. For example:

```sh
dotnet run --project src/Cradle -p:ILGPUBackend=OpenCL
```

Changing the property with `--no-build` cannot change the backend in an existing executable. Native GPU
toolchains are not invoked during the default build; the GPU runtime compiles the embedded source when loading it.

`eng/Cradle.Kernels.targets` imports upstream cleanup, replaces the compilation invocation target to quote
response-file paths, and explicitly orders source swapping after compilation. It rebuilds kernel output each time, removing stale generated
files when launches or backend settings change. The upstream source checkout remains unmodified.
Use explicit class methods and `Main`: the pinned compiler rejects top-level programs containing launches.
Generated Metal code currently produces warnings about embedded source and a hidden inherited member.

To check the integration separately:

```sh
python3 scripts/check_kernel_setup.py
python3 scripts/check_kernel_setup.py --backend Metal
python3 scripts/check_kernel_setup.py --backend CUDA --compile-only
```

The Metal command requires a Metal device and verifies execution. `--compile-only` checks generated source
and its C# wrapper, not native GPU compilation or execution. The available backend names are CPU, CUDA,
ROCm, OpenCL, and Metal. The CPU check is explicitly selected test execution, never a GPU fallback.

Our project restores default to locked mode. `eng/ilgpu-locks/` contains the three upstream project locks
copied into the dependency checkout during setup. For an intentional dependency update, regenerate those
locks and the application/test locks, review their diffs, and validate before committing. Do not bypass locked
restore to get past an unexplained setup failure. ILGPU source and package binaries retain their own licenses.

### The stable CI command

```sh
python3 scripts/check_dotnet.py
```

`.github/workflows/dotnet.yml` invokes this command on Windows, Linux, and macOS. It runs setup (including
the CPU kernel check), then checks kernel generation, builds the current solution, and runs CPU-side tests
for each of CUDA/ROCm/OpenCL/Metal. The final build and test use the platform default. All commands run
locally too; their package versions and compiler pin are identical to the application's.

The hosted workflow does not run the GPU application. Validate GPU execution with
`dotnet run --project src/Cradle`, adding the backend property when needed. That is the same execution
path used in the lesson. Keep numerical checks in the growing program and add CPU-side tests to the test
project as needed; neither requires a new workflow for each article. Source generation alone does not
validate a GPU driver or native kernel execution.

## Site requirements


Requirements: **Hugo 0.154.2** and **Python 3.11 or newer**. No Python packages, Node, or .NET SDK are needed for the site. CI uses Python 3.14.5 and verifies the Hugo download against its pinned SHA-256 checksum. Commands below run from the repository root.

## Preview

```sh
python3 scripts/site.py serve --preview
```

Open `http://localhost:1313/`. The article layout specimen is at `/preview/`; the prologue is at `/lessons/00-getting-the-cradle-ready/`. Preview includes drafts and future-dated articles, displays a notice, and tells crawlers not to index the pages. Use `--port 1314` if necessary. Templates, CSS, and data reload automatically. **Restart after editing article or site-page sources**, which are selected and staged at startup.

Omit `--preview` to serve only public content. Production writes `dist/`; preview writes `dist-preview/`. Both are ignored. Never upload preview output.

## Production build

```sh
python3 scripts/site.py build --base-url https://example.org/cradle/
```

Replace the example with the actual deployment URL, including its project subpath and trailing slash. The base URL is required so a release cannot silently publish localhost canonical URLs. The build checks local links, fragments, images, fonts, and accidental local-context disclosure. It rejects published articles with nonexistent code tags or without a configured public repository.

`.github/workflows/site.yml` runs checks on pull requests and main. `.github/workflows/pages.yml` builds and deploys an artifact on main or manual dispatch, deriving the base URL from GitHub Pages. Before the first remote deployment, create the intended repository and choose **GitHub Actions** as its Pages source. Configure `params.repository` in `web/hugo.toml` before publishing the first lesson. The workflow does not create repositories, push tags, or configure the personal site.

## Export one article to the personal site

```sh
python3 scripts/publish_article.py 01-the-cradle --site /path/to/personal-site --dry-run
python3 scripts/publish_article.py 01-the-cradle --site /path/to/personal-site
```

The destination is always explicit; no workstation layout is assumed. It must contain `hugo.yaml` and `content/writing/`.

The exporter:

- Accepts only `draft = false` articles dated today or earlier (UTC), with valid starting and completed code tags.
- Copies `index.md` and only the images named in `publish_assets`. Rejects symlinks and paths escaping the article.
- Represents the prologue as `lesson = 0` and personal-site `part = 0`; lesson numbering stays 1–18. The personal site labels part zero “Prologue” in its series navigation.
- Emits native Hugo JSON front matter with the personal site's `series` and `part` fields, Cradle canonical URL, and source repository, article path, and commit revision. The body stays Markdown, with code snapshot links added and portable lesson links resolved to the personal edition. The destination template must honor `canonicalURL` in both the canonical link and `og:url`.
- For `math = true`, uses the pinned Hugo math renderer to replace formula spans with MathML. Literal fenced/inline code is preserved; the personal edition needs no additional math scripts.
- Requires the selected source files to be committed before writing. Dry runs may inspect uncommitted edits.
- Records destination hashes in `data/cradle-exports/<personal-slug>.json`, outside published content. Commit that record alongside the exported bundle.
- Refuses to replace existing unowned pages, destination edits, extra files, or deleted bundles with outstanding export records. It prunes obsolete assets only from an unchanged, exporter-owned bundle.
- Stages the replacement locally and restores the previous bundle if a write fails.

Review the destination diff, build the personal site with its normal tools, then commit and deploy there separately. The exporter never commits, pushes, or deploys. If it detects destination changes, bring the intended edits back into Cradle first. After reviewing/backing up the destination, remove its generated bundle **and** matching export record to deliberately reset ownership; there is no force-overwrite switch.

## Checks

```sh
python3 -m unittest discover -s scripts/tests -v
python3 scripts/site.py build --base-url https://example.org/cradle/
python3 scripts/site.py build --preview --base-url https://example.org/cradle/
```

Tests use temporary Git repositories and destination sites, including a real Hugo render when Hugo is installed. They do not write into the personal site.
