"""Service layer for article search."""
import asyncpg

from src.article_persistence.models.domain import ArticleSearchResult
from src.article_persistence.repositories.article_repository import ArticleRepository
from src.server.articles.schemas import ArticleSearchParams


class ArticleSearchService:
    """Thin service that delegates article search to the repository layer."""

    def __init__(self, repo: ArticleRepository | None = None):
        self._repo = repo or ArticleRepository()

    async def search(
        self,
        conn: asyncpg.Connection,
        params: ArticleSearchParams,
    ) -> tuple[list[ArticleSearchResult], int]:
        """Search articles and return results with total count for pagination."""
        return await self._repo.search_articles(
            conn,
            q=params.q,
            from_date=params.from_date,
            to_date=params.to_date,
            include_full_text=params.include_full_text,
            page=params.page,
            page_size=params.page_size,
            sort=params.sort,
            order=params.order,
        )
