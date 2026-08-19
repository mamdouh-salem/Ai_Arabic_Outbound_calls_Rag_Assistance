-- Patch: knowledge_base_chunks.embedding is now vector(768) (local
-- sentence-transformers model) instead of vector(3072) (OpenAI). This updates
-- the index and match_chunks() to match. Run after you've already altered the
-- column and re-embedded the KB chunks via embed_kb_chunks.py.

drop index if exists idx_kb_chunks_embedding;
create index idx_kb_chunks_embedding
  on knowledge_base_chunks using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

create or replace function match_chunks(
  query_embedding vector(768),
  query_text text,
  filter_category text,
  match_count_dense int default 20,
  match_count_sparse int default 20,
  rrf_k int default 60,
  match_count int default 5
)
returns table (
  id uuid,
  content text,
  metadata jsonb,
  score double precision
)
language sql
stable
as $$
  with dense as (
    select
      id, content, metadata,
      row_number() over (order by embedding <=> query_embedding) as rnk
    from knowledge_base_chunks
    where metadata->>'category' = filter_category
    order by embedding <=> query_embedding
    limit match_count_dense
  ),
  sparse as (
    select
      id, content, metadata,
      row_number() over (
        order by ts_rank(fts_tokens, websearch_to_tsquery('simple', query_text)) desc
      ) as rnk
    from knowledge_base_chunks
    where metadata->>'category' = filter_category
      and fts_tokens @@ websearch_to_tsquery('simple', query_text)
    order by ts_rank(fts_tokens, websearch_to_tsquery('simple', query_text)) desc
    limit match_count_sparse
  ),
  fused as (
    select
      id,
      max(content) as content,
      max(metadata) as metadata,
      sum(1.0 / (rrf_k + rnk)) as score
    from (
      select * from dense
      union all
      select * from sparse
    ) combined
    group by id
  )
  select id, content, metadata, score
  from fused
  order by score desc
  limit match_count;
$$;
