# Configuration file for the Sphinx documentation builder.

from pathlib import Path

import sys


sys.path.insert(0, str(Path(__file__).parent / "_ext"))

# -- Project information -----------------------------------------------------

project = "plone.observability"
copyright = "2026, BlueDynamics Alliance"  # noqa: A001
author = "Jens Klein and contributors"
release = "1.0.0b13"

# -- General configuration ---------------------------------------------------

extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
    "sphinx_design",
    "sphinx_copybutton",
    "ecosystem_dashboard",
]

myst_enable_extensions = [
    "deflist",
    "colon_fence",
    "fieldlist",
]

myst_fence_as_directive = ["mermaid"]

templates_path = ["_templates"]
exclude_patterns = []

# mermaid options
mermaid_output_format = "raw"

# -- Options for HTML output -------------------------------------------------

html_theme = "shibuya"

html_theme_options = {
    "logo_target": "/plone.observability/",
    "accent_color": "cyan",
    "color_mode": "dark",
    "dark_code": True,
    "nav_links": [
        {
            "title": "Ecosystem",
            "url": "https://plone.github.io/plone.observability/ecosystem.html",
            "children": [
                {
                    "title": "Dashboard",
                    "url": "https://plone.github.io/plone.observability/ecosystem.html",
                    "summary": "Overview of all packages",
                },
                {
                    "title": "plone.observability",
                    "url": "https://plone.github.io/plone.observability/",
                    "summary": "Health probes, metrics, and tracing",
                },
                {
                    "title": "zodb-pgjsonb",
                    "url": "https://bluedynamics.github.io/zodb-pgjsonb/",
                    "summary": "PostgreSQL JSONB storage",
                },
                {
                    "title": "zodb-json-codec",
                    "url": "https://bluedynamics.github.io/zodb-json-codec/",
                    "summary": "Rust pickle↔JSON transcoder",
                },
                {
                    "title": "plone-pgcatalog",
                    "url": "https://bluedynamics.github.io/plone-pgcatalog/",
                    "summary": "PostgreSQL-backed catalog",
                },
                {
                    "title": "plone-pgthumbor",
                    "url": "https://bluedynamics.github.io/plone-pgthumbor/",
                    "summary": "Thumbor image scaling",
                },
                {
                    "title": "cdk8s-plone",
                    "url": "https://bluedynamics.github.io/cdk8s-plone/",
                    "summary": "Deploy Plone to Kubernetes",
                },
            ],
        },
        {
            "title": "GitHub",
            "url": "https://github.com/plone/plone.observability",
        },
        {
            "title": "PyPI",
            "url": "https://pypi.org/project/plone.observability/",
        },
    ],
}

html_extra_path = ["llms.txt"]
html_static_path = ["_static"]
html_logo = "_static/logo-web.png"
html_favicon = "_static/favicon.ico"
