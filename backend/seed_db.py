"""
Toxic Pulse — ChromaDB Seeder

Reads markdown docs from ../data/docs/, chunks them, and embeds
into 3 ChromaDB collections: permits, agriculture, watershed.

Run from the backend directory:
    python seed_db.py
"""

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Imports (with helpful error messages if deps are missing)
# ---------------------------------------------------------------------------
try:
    # langchain >= 0.2 moved text splitters to langchain_text_splitters
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
except ImportError:
    print(
        "ERROR: langchain text splitters not installed. "
        "Run: pip install langchain-text-splitters",
        file=sys.stderr,
    )
    raise

try:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
except ImportError:
    print("ERROR: chromadb not installed. Run: pip install chromadb", file=sys.stderr)
    raise

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOCS_DIR = Path(__file__).parent.parent / "data" / "docs"
CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma_db"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Mapping from filename stem to (document_type, target_collection)
FILENAME_META: dict[str, tuple[str, str]] = {
    "epa_permits":         ("permits",    "permits"),
    "who_guidelines":      ("guidelines", "permits"),
    "agricultural_zones":  ("agriculture","agriculture"),
    "watershed_maps":      ("watershed",  "watershed"),
    "historical_incidents":("incidents",  "watershed"),
}

# Keywords used to infer region from chunk text
REGION_KEYWORDS: dict[str, list[str]] = {
    "lake_erie": [
        "lake erie", "toledo", "maumee", "western basin", "ohio",
        "davis-besse", "bp husky", "collins park", "cuyahoga",
        "sandusky", "portage river", "great lakes",
    ],
    "lake_victoria": [
        "lake victoria", "kisumu", "mwanza", "entebbe", "kagera",
        "winam gulf", "nzoia", "yala", "nile perch", "uganda",
        "kenya", "tanzania", "victoria nile", "east africa",
    ],
    "mekong_delta": [
        "mekong", "can tho", "hau river", "tien river", "vietnam",
        "mekong delta", "my tho", "ca mau", "shrimp", "rang dong",
        "monsoon", "south china sea", "saigon",
    ],
}


def infer_region(text: str) -> str:
    """Return the most likely region for a chunk of text, or 'global'."""
    text_lower = text.lower()
    scores = {region: 0 for region in REGION_KEYWORDS}
    for region, keywords in REGION_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[region] += 1
    best_region = max(scores, key=lambda r: scores[r])
    return best_region if scores[best_region] > 0 else "global"


# ---------------------------------------------------------------------------
# Core seeding logic
# ---------------------------------------------------------------------------

def seed():
    print("=== Toxic Pulse — ChromaDB Seeder ===\n")

    # Validate docs directory
    if not DOCS_DIR.exists():
        print(f"ERROR: docs directory not found: {DOCS_DIR}", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(DOCS_DIR.glob("*.md"))
    if not md_files:
        print(f"ERROR: No .md files found in {DOCS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(md_files)} document(s) in {DOCS_DIR}:")
    for f in md_files:
        print(f"  {f.name}")
    print()

    # ---------------------------------------------------------------------------
    # Text splitter
    # ---------------------------------------------------------------------------
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # ---------------------------------------------------------------------------
    # Read and chunk all documents
    # ---------------------------------------------------------------------------
    all_chunks: list[tuple[str, dict]] = []  # (text, metadata)

    for md_path in md_files:
        stem = md_path.stem  # e.g. "epa_permits"

        if stem not in FILENAME_META:
            print(f"  WARN: '{md_path.name}' not in FILENAME_META — skipping.")
            continue

        doc_type, collection_name = FILENAME_META[stem]
        raw_text = md_path.read_text(encoding="utf-8")
        chunks = splitter.split_text(raw_text)

        print(f"  {md_path.name}: {len(raw_text):,} chars -> {len(chunks)} chunks "
              f"(doc_type={doc_type}, collection={collection_name})")

        for i, chunk_text in enumerate(chunks):
            region = infer_region(chunk_text)
            metadata = {
                "source":        md_path.name,
                "region":        region,
                "document_type": doc_type,
                "collection":    collection_name,
                "chunk_index":   i,
            }
            all_chunks.append((chunk_text, metadata))

    print(f"\nTotal chunks to embed: {len(all_chunks)}\n")

    # ---------------------------------------------------------------------------
    # ChromaDB setup
    # ---------------------------------------------------------------------------
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"ChromaDB path: {CHROMA_DIR}")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embedding_fn = SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    # Create (or get existing) collections
    collections: dict[str, chromadb.Collection] = {}
    for coll_name in ("permits", "agriculture", "watershed"):
        coll = client.get_or_create_collection(
            name=coll_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        collections[coll_name] = coll
        print(f"  Collection '{coll_name}': {coll.count()} existing documents")
    print()

    # ---------------------------------------------------------------------------
    # Upsert chunks into the correct collection
    # ---------------------------------------------------------------------------
    # Group chunks by collection
    by_collection: dict[str, list[tuple[str, dict, str]]] = {
        "permits": [],
        "agriculture": [],
        "watershed": [],
    }

    for idx, (text, meta) in enumerate(all_chunks):
        coll_name = meta["collection"]
        # Deterministic chunk ID: source_file + chunk_index
        chunk_id = f"{meta['source'].replace('.', '_')}_{meta['chunk_index']:04d}"
        by_collection[coll_name].append((chunk_id, text, meta))

    BATCH_SIZE = 64

    total_added = 0
    for coll_name, items in by_collection.items():
        if not items:
            print(f"  Collection '{coll_name}': no chunks to add.")
            continue

        coll = collections[coll_name]
        print(f"  Upserting {len(items)} chunks into '{coll_name}' ...")

        # Batch upsert
        for batch_start in range(0, len(items), BATCH_SIZE):
            batch = items[batch_start: batch_start + BATCH_SIZE]
            ids        = [b[0] for b in batch]
            documents  = [b[1] for b in batch]
            metadatas  = [b[2] for b in batch]

            coll.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )

        total_added += len(items)
        print(f"    Done. '{coll_name}' now has {coll.count()} documents.")

    print(f"\nSeeding complete. {total_added} chunks upserted across 3 collections.")

    # ---------------------------------------------------------------------------
    # Final summary
    # ---------------------------------------------------------------------------
    print("\n=== Collection Summary ===")
    for coll_name, coll in collections.items():
        count = coll.count()
        print(f"  {coll_name:15s}: {count:4d} documents")
    print()


if __name__ == "__main__":
    seed()
