select
    md5(game_title || platform_name || cast(snapshot_date as varchar))  as sale_id,
    md5(game_title)      as game_id,
    md5(platform_name)   as platform_id,
    snapshot_date,
    fiscal_year,
    global_sales,
    japan_sales,
    outside_japan_sales,
    ltd_global_sales,
    source
from "nintendo_sales"."silver"."stg_million_sellers"