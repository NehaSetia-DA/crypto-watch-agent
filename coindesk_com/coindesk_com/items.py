from dataclasses import dataclass, field


@dataclass
class NavigationLink:
    url: str | None = None
    text: str | None = None


@dataclass
class Navigation:
    items: list[NavigationLink] | None = None
    next_page: str | None = None
    subcategories: list[NavigationLink] | None = None


@dataclass
class Article:
    headline: str | None = None
    author: str | None = None
    date_published: str | None = None
    body: str | None = None
    url: str | None = None
    subheadline: str | None = None
    section: str | None = None
    author_url: str | None = None
    author_job_title: str | None = None
    author_bio: str | None = None
    editor_name: str | None = None
    date_modified: str | None = None
    read_time: str | None = None
    hero_image_url: str | None = None
    hero_image_caption: str | None = None
    what_to_know: list[str] | None = None
    article_body_html: str | None = None
    tags: list[str] | None = None
    keywords: list[str] | None = None
    article_id: str | None = None
