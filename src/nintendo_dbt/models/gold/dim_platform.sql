select distinct
    md5(platform_name)  as platform_id,
    platform_name       as name
from {{ source('silver', 'stg_million_sellers') }}
