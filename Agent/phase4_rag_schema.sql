-- Phase 4: RAG Schema
-- Enable the pgvector extension to work with embeddings
create extension if not exists vector;

-- Create a table to store document chunks and their embeddings
create table if not exists document_sections (
  id bigserial primary key,
  content text not null,
  metadata jsonb default '{}'::jsonb,
  embedding vector(384) -- Based on all-MiniLM-L6-v2 (384 dimensions)
);

-- Index for fast semantic search
create index on document_sections using hnsw (embedding vector_cosine_ops);

-- Function to perform semantic search
create or replace function match_documents (
  query_embedding vector(384),
  match_threshold float,
  match_count int
)
returns table (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    ds.id,
    ds.content,
    ds.metadata,
    1 - (ds.embedding <=> query_embedding) as similarity
  from document_sections ds
  where 1 - (ds.embedding <=> query_embedding) > match_threshold
  order by similarity desc
  limit match_count;
end;
$$;
