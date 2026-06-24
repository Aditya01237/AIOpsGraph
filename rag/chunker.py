import os
import re
import json
import argparse
from typing import List, Dict, Any


KNOWLEDGE_BASE_DIR = "knowledge_base"
OUTPUT_DIR = "data/chunks"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "knowledge_chunks.json")

SUPPORTED_EXTENSIONS = {".md", ".txt"}


def read_text_file(path: str) -> str:
    """
    Read a text or markdown file.
    """
    with open(path, "r") as f:
        return f.read()


def discover_documents(input_dir: str) -> List[str]:
    """
    Find all markdown/text files inside knowledge_base.
    """
    documents = []

    if not os.path.exists(input_dir):
        raise FileNotFoundError(
            f"Knowledge base folder not found: {input_dir}"
        )

    for root, _, files in os.walk(input_dir):
        for file in files:
            extension = os.path.splitext(file)[1]

            if extension in SUPPORTED_EXTENSIONS:
                documents.append(os.path.join(root, file))

    documents.sort()
    return documents


def clean_id(text: str) -> str:
    """
    Convert text/path into safe chunk id.
    """
    text = text.lower()
    text = text.replace("/", "_")
    text = text.replace("\\", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def extract_document_title(content: str, fallback: str) -> str:
    """
    Extract first markdown heading as document title.
    """
    for line in content.splitlines():
        line = line.strip()

        if line.startswith("#"):
            return line.lstrip("#").strip()

    return fallback


def split_markdown_into_sections(content: str) -> List[Dict[str, str]]:
    """
    Split markdown content using headings.

    Example:
    # CrashLoopBackOff
    ## Meaning
    ## Common Causes

    Each heading section becomes a section.
    """
    sections = []

    current_title = "Introduction"
    current_lines = []

    for line in content.splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)

        if heading_match:
            if current_lines:
                sections.append({
                    "section_title": current_title,
                    "content": "\n".join(current_lines).strip()
                })

            current_title = heading_match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "section_title": current_title,
            "content": "\n".join(current_lines).strip()
        })

    return [
        section for section in sections
        if section.get("content")
    ]


def split_large_text(
    text: str,
    max_chars: int,
    overlap: int
) -> List[str]:
    """
    Split large text into smaller chunks.

    max_chars controls chunk size.
    overlap keeps small repeated context between chunks.
    """
    if len(text) <= max_chars:
        return [text.strip()]

    if overlap >= max_chars:
        overlap = max_chars // 5

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + max_chars, len(text))

        cut_position = text.rfind("\n\n", start, end)

        if cut_position == -1 or cut_position <= start + max_chars // 2:
            cut_position = end
        else:
            cut_position += 2

        chunk = text[start:cut_position].strip()

        if chunk:
            chunks.append(chunk)

        if cut_position >= len(text):
            break

        start = max(0, cut_position - overlap)

    return chunks


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate.

    Not exact, but good enough for metadata.
    """
    return max(1, len(text.split()))


def extract_basic_keywords(text: str) -> List[str]:
    """
    Extract simple useful keywords from chunk text.
    """
    known_keywords = [
        "crashloopbackoff",
        "imagepullbackoff",
        "errimagepull",
        "oomkilled",
        "exit code 137",
        "memory",
        "restart",
        "pod",
        "container",
        "event",
        "logs",
        "previous logs",
        "configmap",
        "secret",
        "imagepullsecret",
        "registry",
        "kubectl",
        "cgroup",
        "sigkill",
        "backoff",
        "failed",
    ]

    text_lower = text.lower()
    matched_keywords = []

    for keyword in known_keywords:
        if keyword in text_lower:
            matched_keywords.append(keyword)

    return matched_keywords


def build_chunks_from_document(
    path: str,
    content: str,
    max_chars: int,
    overlap: int
) -> List[Dict[str, Any]]:
    """
    Convert one document into multiple chunks.
    """
    document_title = extract_document_title(
        content,
        fallback=os.path.basename(path)
    )

    sections = split_markdown_into_sections(content)

    chunks = []
    local_chunk_index = 0

    for section in sections:
        section_title = section.get("section_title", "Unknown Section")
        section_content = section.get("content", "")

        smaller_chunks = split_large_text(
            text=section_content,
            max_chars=max_chars,
            overlap=overlap
        )

        for chunk_text in smaller_chunks:
            chunk_id = (
                f"{clean_id(path)}"
                f"__section_{clean_id(section_title)}"
                f"__chunk_{local_chunk_index}"
            )

            chunk = {
                "chunk_id": chunk_id,
                "source_path": path,
                "source_file": os.path.basename(path),
                "document_title": document_title,
                "section_title": section_title,
                "chunk_index": local_chunk_index,
                "content": chunk_text,
                "char_count": len(chunk_text),
                "token_estimate": estimate_tokens(chunk_text),
                "keywords": extract_basic_keywords(chunk_text)
            }

            chunks.append(chunk)
            local_chunk_index += 1

    return chunks


def build_all_chunks(
    input_dir: str,
    max_chars: int,
    overlap: int
) -> List[Dict[str, Any]]:
    """
    Build chunks from all knowledge base documents.
    """
    documents = discover_documents(input_dir)

    all_chunks = []

    for document_path in documents:
        content = read_text_file(document_path)

        document_chunks = build_chunks_from_document(
            path=document_path,
            content=content,
            max_chars=max_chars,
            overlap=overlap
        )

        all_chunks.extend(document_chunks)

    return all_chunks


def save_chunks(chunks: List[Dict[str, Any]], output_file: str) -> None:
    """
    Save chunks as JSON.
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    output_data = {
        "metadata": {
            "total_chunks": len(chunks),
            "description": "Knowledge base chunks generated for AIOpsGraph retrieval"
        },
        "chunks": chunks
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"Saved chunks: {output_file}")


def print_summary(chunks: List[Dict[str, Any]]) -> None:
    """
    Print chunking summary.
    """
    print("\nChunking Summary")
    print("----------------")
    print(f"Total chunks: {len(chunks)}")

    file_count = {}

    for chunk in chunks:
        source_file = chunk.get("source_file")
        file_count[source_file] = file_count.get(source_file, 0) + 1

    print("\nChunks by file")
    print("--------------")

    for source_file, count in sorted(file_count.items()):
        print(f"{source_file}: {count}")


def print_preview(chunks: List[Dict[str, Any]], limit: int) -> None:
    """
    Print first few chunks for checking.
    """
    if limit <= 0:
        return

    print("\nChunk Preview")
    print("-------------")

    for index, chunk in enumerate(chunks[:limit], start=1):
        print(f"\nChunk {index}")
        print(f"ID: {chunk.get('chunk_id')}")
        print(f"Source: {chunk.get('source_path')}")
        print(f"Section: {chunk.get('section_title')}")
        print(f"Keywords: {chunk.get('keywords')}")
        print("Content:")
        print(chunk.get("content", "")[:500])


def main():
    parser = argparse.ArgumentParser(
        description="Chunk AIOpsGraph knowledge base documents"
    )

    parser.add_argument(
        "--input-dir",
        type=str,
        default=KNOWLEDGE_BASE_DIR,
        help="Knowledge base input folder"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=OUTPUT_FILE,
        help="Output chunks JSON file"
    )

    parser.add_argument(
        "--max-chars",
        type=int,
        default=1200,
        help="Maximum characters per chunk"
    )

    parser.add_argument(
        "--overlap",
        type=int,
        default=150,
        help="Character overlap between chunks"
    )

    parser.add_argument(
        "--preview",
        type=int,
        default=3,
        help="Number of chunks to preview"
    )

    args = parser.parse_args()

    chunks = build_all_chunks(
        input_dir=args.input_dir,
        max_chars=args.max_chars,
        overlap=args.overlap
    )

    save_chunks(chunks, args.output)
    print_summary(chunks)
    print_preview(chunks, args.preview)


if __name__ == "__main__":
    main()