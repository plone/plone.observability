Deploy the documentation on `release: published` as well, so every release
republishes the docs with the freshly bumped version. Release PRs do not touch
`docs/**`, so the push trigger alone left the site on the previous version
until the next docs commit.
