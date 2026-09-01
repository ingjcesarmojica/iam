"""
Script para subir documentos de conocimiento de IAM a Pinecone.
Uso: python upload_knowledge.py

Coloca los PDFs que quieras subir en esta misma carpeta con un nombre que
empiece por 'conocimiento_iam' (por ejemplo: conocimiento_iam.pdf) y el script
los indexará automáticamente en el índice 'iam-conocimiento' de Pinecone.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from rag import add_pdf, list_documents, delete_document


def main():
    print("=== Subir Documento de Conocimiento de IAM a Pinecone ===\n")

    docs_dir = os.path.dirname(os.path.abspath(__file__))

    # Buscar todos los PDFs cuyo nombre empiece por 'conocimiento_iam'
    pdf_files = sorted(
        os.path.join(docs_dir, f)
        for f in os.listdir(docs_dir)
        if f.lower().endswith(".pdf") and f.lower().startswith("conocimiento_iam")
    )

    if not pdf_files:
        print("No se encontraron PDFs de conocimiento de IAM en esta carpeta.")
        print("Coloca archivos con nombre 'conocimiento_iam*.pdf' aquí.")
        return

    print("Documentos actuales en Pinecone:")
    existing = list_documents()
    if existing:
        for doc in existing:
            print(f"  - {doc}")
    else:
        print("  (ninguno)")
    print()

    if existing:
        resp = input(
            "¿Desea eliminar los documentos existentes antes de subir? (s/n): "
        )
        if resp.lower() == "s":
            for doc in existing:
                ok, msg = delete_document(doc)
                print(f"  Eliminado: {msg}")

    for pdf_file in pdf_files:
        print(f"\nSubiendo PDF: {pdf_file}")
        count, msg = add_pdf(pdf_file)  # source_name toma el basename
        print(f"  Resultado: {msg}")

    print("\nDocumentos en Pinecone después de subir:")
    final_docs = list_documents()
    if final_docs:
        for doc in final_docs:
            print(f"  - {doc}")
    else:
        print("  (ninguno)")

    print("\nListo.")


if __name__ == "__main__":
    main()
