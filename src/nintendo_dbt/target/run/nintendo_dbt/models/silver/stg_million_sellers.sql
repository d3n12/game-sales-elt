
  
  create view "nintendo_sales"."silver"."stg_million_sellers__dbt_tmp" as (
    with source as (
    select * from "nintendo_sales"."bronze"."raw_million_sellers"
),

cleaned as (
    select
        array_to_string(
            list_transform(
                string_split_regex(
                    regexp_replace(replace(replace(replace(lower("Game Title"), chr(8217), chr(39)), chr(700), chr(39)), chr(8211), ''), '\s*/\s*', ' / '),
                    '\s+'
                ),
                w -> upper(left(w, 1)) || substr(w, 2)
            ),
            ' '
        )                                                              as game_title,
        "system"                                                       as platform_name,
        "Fiscal Year"                                                  as fiscal_year,
        cast("as of" as date)                                          as snapshot_date,
        try_cast(replace("Global", ',', '')              as integer) * 10000 as global_sales,
        try_cast(replace("Japan", ',', '')               as integer) * 10000 as japan_sales,
        try_cast(replace("Outside of Japan", ',', '')    as integer) * 10000 as outside_japan_sales,
        try_cast(replace("Life-to-date Global", ',', '') as integer) * 10000 as ltd_global_sales,
        source
    from source
    where
        "Game Title" is not null
        and "Game Title" not in ('-', '')
)

select * from cleaned
  );
