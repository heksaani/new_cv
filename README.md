# Heidi Putkuri – portfolio

Live site: https://heksaani.github.io/new_cv/

The site is plain HTML and CSS with no build step:

```
public/
  index.html      all content (hero, career track, projects, experience, skills)
  style.css       design, light/dark theme and the print layout for the CV
  fonts/          self-hosted Bricolage Grotesque and Public Sans (SIL OFL)
  images/         project images and favicon
```

Every push to `main` deploys `public/` to GitHub Pages (`.github/workflows/docs.yml`).

## Preview locally

```bash
cd public
python3 -m http.server 8000
# open http://localhost:8000
```

## Common edits

**Add a project.** Copy one `<article class="project with-figure">` block in
`index.html`, change the texts and links, and put its image in `public/images/`.
Drop the `<figure>` and use `class="project"` if it has no image.

**Update the career track.** Each bar is an `<a class="feat">` with a start and
end year as decimals, for example `style="--s:2025.5; --e:2026.82"` (July 2025 is
2025.5). `--now` on `.track-inner` sets the red "now" line. Add `open` to the
class for an ongoing role and `planned` for something that continues into the
future.

**Save the CV as a PDF.** The "Save CV as PDF" button opens the browser's print
dialog; the print stylesheet reorders the page into a CV (experience, skills,
projects) and hides the interactive parts.

## Old Zensical version

`docs/`, `zensical.toml`, `pyproject.toml`, `uv.lock` and `site/` belong to the
previous Zensical site and are no longer used by the deployment. They can be
deleted.
