select distinct
    md5(game_title)  as game_id,
    game_title       as title
from "nintendo_sales"."silver"."stg_million_sellers"