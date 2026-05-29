
  
    
    

    create  table
      "nintendo_sales"."gold"."dim_game__dbt_tmp"
  
    as (
      select distinct
    md5(game_title)  as game_id,
    game_title       as title
from "nintendo_sales"."silver"."stg_million_sellers"
    );
  
  