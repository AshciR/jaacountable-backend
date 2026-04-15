"""
Benchmark classification latency across multiple LLM models.

Classifies the same set of articles with each model and compares:
- Per-article latency (mean, median, p95)
- Classification quality (is_relevant, confidence, reasoning)
- Estimated cost per 1000 articles

Usage:
    uv run python scripts/testing/benchmark_classification_models.py \
        --input scripts/production/discovery/output/jamaica_observer_discovery_2026-01-01_to_2026-04-14_2026-04-14_21-24-14.jsonl \
        --sample-size 10

    # Test specific models only
    uv run python scripts/testing/benchmark_classification_models.py \
        --input articles.jsonl \
        --models gpt-4o-mini gpt-5.4-nano
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from src.article_classification.base import CLASSIFICATION_API_KEY
from src.article_classification.agents.corruption_agent import instruction
from src.article_classification.classifiers.corruption_classifier import (
    CorruptionClassifier,
)
from src.article_classification.converters import (
    extracted_content_to_classification_input,
)
from src.article_classification.models import ClassificationInput, ClassificationResult
from src.article_discovery.models import DiscoveredArticle
from src.article_extractor.service import DefaultArticleExtractionService


# Pricing per 1M tokens (input, output)
MODEL_PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5.4-nano": (0.20, 1.25),
}

# Default models to benchmark
DEFAULT_MODELS = ["gpt-4o-mini", "gpt-5-nano", "gpt-5.4-nano"]


@dataclass
class ArticleResult:
    """Result of classifying a single article with a single model."""

    url: str
    latency_seconds: float
    result: ClassificationResult | None = None
    error: str | None = None


@dataclass
class ModelBenchmark:
    """Aggregated benchmark results for a single model."""

    model_name: str
    article_results: list[ArticleResult] = field(default_factory=list)

    @property
    def successful_results(self) -> list[ArticleResult]:
        return [r for r in self.article_results if r.result is not None]

    @property
    def failed_results(self) -> list[ArticleResult]:
        return [r for r in self.article_results if r.error is not None]

    @property
    def latencies(self) -> list[float]:
        return [r.latency_seconds for r in self.successful_results]

    @property
    def mean_latency(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0.0

    @property
    def median_latency(self) -> float:
        return statistics.median(self.latencies) if self.latencies else 0.0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_l = sorted(self.latencies)
        idx = int(len(sorted_l) * 0.95)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    @property
    def relevant_count(self) -> int:
        return sum(
            1 for r in self.successful_results if r.result and r.result.is_relevant
        )


def load_jsonl_articles(file_path: Path) -> list[DiscoveredArticle]:
    """Load articles from JSONL file."""
    articles = []
    with open(file_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            article_dict = json.loads(line)
            article = DiscoveredArticle.model_validate(article_dict)
            articles.append(article)
    return articles


def create_classifier_for_model(model_name: str) -> CorruptionClassifier:
    """Create a CorruptionClassifier wired to a specific model."""
    # Build the instruction with the benchmark model name substituted
    # The original instruction uses f-string with CLASSIFICATION_MODEL at import time,
    # so we need to rebuild it with the target model name for the JSON output template
    benchmark_instruction = instruction.replace(
        f'"model_name": "{_get_current_model_in_instruction()}"',
        f'"model_name": "{model_name}"',
    )

    agent = LlmAgent(
        model=LiteLlm(model=model_name, api_key=CLASSIFICATION_API_KEY),
        name=f"corruption_classifier_{model_name.replace('-', '_').replace('.', '_')}",
        description="Benchmark corruption classifier",
        instruction=benchmark_instruction,
    )
    return CorruptionClassifier(agent=agent)


def _get_current_model_in_instruction() -> str:
    """Extract the model name currently baked into the instruction f-string."""
    # The instruction contains: "model_name": "<MODEL>"
    # Find it by looking for the pattern
    marker = '"model_name": "'
    idx = instruction.find(marker)
    if idx == -1:
        return "gpt-5-nano"  # fallback
    start = idx + len(marker)
    end = instruction.find('"', start)
    return instruction[start:end]


async def extract_article(
    extractor: DefaultArticleExtractionService,
    article: DiscoveredArticle,
) -> ClassificationInput | None:
    """Extract and convert an article to ClassificationInput."""
    try:
        extracted = await extractor.extract_article_content(article.url)
        return extracted_content_to_classification_input(
            extracted=extracted,
            url=article.url,
            section=article.section,
        )
    except Exception as e:
        print(f"  Extraction failed for {article.url}: {e}")
        return None


async def benchmark_model(
    model_name: str,
    articles: list[ClassificationInput],
    console: Console,
) -> ModelBenchmark:
    """Benchmark a single model against all articles."""
    benchmark = ModelBenchmark(model_name=model_name)
    classifier = create_classifier_for_model(model_name)

    console.print(f"\n[bold cyan]Benchmarking: {model_name}[/bold cyan]")

    for i, article in enumerate(articles, 1):
        console.print(
            f"  [{i}/{len(articles)}] {article.url[:80]}...", end=" "
        )

        start = time.perf_counter()
        try:
            result = await classifier.classify(article)
            elapsed = time.perf_counter() - start
            benchmark.article_results.append(
                ArticleResult(
                    url=article.url,
                    latency_seconds=elapsed,
                    result=result,
                )
            )
            relevant_marker = "[green]RELEVANT[/green]" if result.is_relevant else "[dim]not relevant[/dim]"
            console.print(
                f"[yellow]{elapsed:.1f}s[/yellow] | {relevant_marker} | conf={result.confidence:.2f}"
            )
        except Exception as e:
            elapsed = time.perf_counter() - start
            benchmark.article_results.append(
                ArticleResult(
                    url=article.url,
                    latency_seconds=elapsed,
                    error=str(e),
                )
            )
            console.print(f"[red]ERROR ({elapsed:.1f}s): {e}[/red]")

    return benchmark


def print_summary_table(benchmarks: list[ModelBenchmark], console: Console):
    """Print comparison table of all model benchmarks."""
    table = Table(
        title="Model Benchmark Comparison",
        box=box.ROUNDED,
        show_lines=True,
    )

    table.add_column("Model", style="bold cyan")
    table.add_column("Mean Latency", justify="right")
    table.add_column("Median Latency", justify="right")
    table.add_column("P95 Latency", justify="right")
    table.add_column("Success", justify="right")
    table.add_column("Relevant", justify="right")
    table.add_column("Est. Cost/1K articles", justify="right")

    for bm in benchmarks:
        # Rough cost estimate: assume ~1500 input tokens, ~200 output tokens per article
        input_tokens_per_article = 1500
        output_tokens_per_article = 200
        pricing = MODEL_PRICING.get(bm.model_name, (0.0, 0.0))
        cost_per_1k = (
            (input_tokens_per_article * 1000 / 1_000_000) * pricing[0]
            + (output_tokens_per_article * 1000 / 1_000_000) * pricing[1]
        )

        table.add_row(
            bm.model_name,
            f"{bm.mean_latency:.2f}s",
            f"{bm.median_latency:.2f}s",
            f"{bm.p95_latency:.2f}s",
            f"{len(bm.successful_results)}/{len(bm.article_results)}",
            f"{bm.relevant_count}/{len(bm.successful_results)}",
            f"${cost_per_1k:.3f}",
        )

    console.print()
    console.print(table)


def print_detailed_comparison(
    benchmarks: list[ModelBenchmark], console: Console
):
    """Print per-article comparison across models."""
    table = Table(
        title="Per-Article Comparison",
        box=box.ROUNDED,
        show_lines=True,
    )

    table.add_column("Article URL", max_width=50)
    for bm in benchmarks:
        table.add_column(f"{bm.model_name}\nRelevant | Conf | Time", justify="center")

    # Build URL-indexed lookup for each model
    model_results: dict[str, dict[str, ArticleResult]] = {}
    for bm in benchmarks:
        model_results[bm.model_name] = {r.url: r for r in bm.article_results}

    # Get all URLs from the first benchmark
    if not benchmarks:
        return

    urls = [r.url for r in benchmarks[0].article_results]

    for url in urls:
        row = [url[:50] + "..." if len(url) > 50 else url]
        for bm in benchmarks:
            ar = model_results[bm.model_name].get(url)
            if ar and ar.result:
                relevant = "Y" if ar.result.is_relevant else "N"
                row.append(
                    f"{relevant} | {ar.result.confidence:.2f} | {ar.latency_seconds:.1f}s"
                )
            elif ar and ar.error:
                row.append(f"[red]ERROR[/red]")
            else:
                row.append("-")
        table.add_row(*row)

    console.print()
    console.print(table)


def print_reasoning_samples(benchmarks: list[ModelBenchmark], console: Console):
    """Print reasoning from each model for the first 3 articles."""
    console.print("\n[bold]Reasoning Samples (first 3 articles):[/bold]\n")

    sample_count = min(3, len(benchmarks[0].article_results) if benchmarks else 0)

    for i in range(sample_count):
        url = benchmarks[0].article_results[i].url
        console.print(f"[bold yellow]Article {i+1}:[/bold yellow] {url[:80]}")

        for bm in benchmarks:
            ar = bm.article_results[i] if i < len(bm.article_results) else None
            if ar and ar.result:
                console.print(f"  [cyan]{bm.model_name}:[/cyan] {ar.result.reasoning}")
            elif ar and ar.error:
                console.print(f"  [cyan]{bm.model_name}:[/cyan] [red]ERROR: {ar.error}[/red]")
        console.print()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Benchmark classification latency across LLM models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to JSONL file with discovered articles",
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Number of articles to sample for benchmarking (default: 10)",
    )

    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help=f"Models to benchmark (default: {' '.join(DEFAULT_MODELS)})",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for article sampling (default: 42, for reproducibility)",
    )

    args = parser.parse_args()

    if not args.input.exists():
        parser.error(f"Input file does not exist: {args.input}")

    if args.sample_size < 1:
        parser.error("--sample-size must be at least 1")

    return args


async def main() -> int:
    load_dotenv()

    args = parse_args()
    console = Console()

    # Load and sample articles
    console.print(f"[bold]Loading articles from {args.input}...[/bold]")
    all_articles = load_jsonl_articles(args.input)
    console.print(f"Loaded {len(all_articles)} articles")

    random.seed(args.seed)
    sample = random.sample(all_articles, min(args.sample_size, len(all_articles)))
    console.print(f"Sampled {len(sample)} articles (seed={args.seed})")

    # Extract all sampled articles once (shared across all models)
    console.print("\n[bold]Extracting article content...[/bold]")
    extractor = DefaultArticleExtractionService()
    classification_inputs: list[ClassificationInput] = []

    for i, article in enumerate(sample, 1):
        console.print(f"  [{i}/{len(sample)}] Extracting {article.url[:80]}...")
        ci = await extract_article(extractor, article)
        if ci:
            classification_inputs.append(ci)

    if not classification_inputs:
        console.print("[red]No articles could be extracted. Exiting.[/red]")
        return 1

    console.print(
        f"\n[bold green]Successfully extracted {len(classification_inputs)}/{len(sample)} articles[/bold green]"
    )

    # Benchmark each model sequentially
    benchmarks: list[ModelBenchmark] = []
    for model_name in args.models:
        bm = await benchmark_model(model_name, classification_inputs, console)
        benchmarks.append(bm)

    # Print results
    print_summary_table(benchmarks, console)
    print_detailed_comparison(benchmarks, console)
    print_reasoning_samples(benchmarks, console)

    # Print projected batch times
    console.print("\n[bold]Projected batch times for 7,179 articles:[/bold]")
    for bm in benchmarks:
        if bm.mean_latency > 0:
            for concurrency in [4, 8, 10]:
                total_seconds = (7179 / concurrency) * bm.mean_latency
                hours = total_seconds / 3600
                console.print(
                    f"  {bm.model_name} @ concurrency {concurrency}: "
                    f"[yellow]{hours:.1f} hours[/yellow] ({total_seconds/60:.0f} min)"
                )
        console.print()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
