SELECT
    cid,
    name AS column_name,
    type AS column_type,
    "notnull" AS not_null,
    pk AS is_primary_key
FROM pragma_table_info('user_behavior_processed');

SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT user_id) AS unique_users,
    COUNT(DISTINCT item_id) AS unique_items,
    COUNT(DISTINCT item_category) AS unique_categories,
    COUNT(DISTINCT behavior_type) AS behavior_type_count,
    MIN(time) AS min_time,
    MAX(time) AS max_time
FROM user_behavior_processed;

SELECT
    SUM(CASE WHEN time IS NULL OR TRIM(CAST(time AS TEXT)) = '' THEN 1 ELSE 0 END) AS missing_time,
    SUM(CASE WHEN user_id IS NULL OR TRIM(CAST(user_id AS TEXT)) = '' THEN 1 ELSE 0 END) AS missing_user_id,
    SUM(CASE WHEN item_id IS NULL OR TRIM(CAST(item_id AS TEXT)) = '' THEN 1 ELSE 0 END) AS missing_item_id,
    SUM(CASE WHEN item_category IS NULL OR TRIM(CAST(item_category AS TEXT)) = '' THEN 1 ELSE 0 END) AS missing_item_category,
    SUM(CASE WHEN behavior_type IS NULL OR TRIM(CAST(behavior_type AS TEXT)) = '' THEN 1 ELSE 0 END) AS missing_behavior_type
FROM user_behavior_processed;

SELECT
    behavior_type,
    CASE
        WHEN behavior_type = 1 THEN 'numeric_code: pv'
        WHEN behavior_type = 2 THEN 'numeric_code: fav'
        WHEN behavior_type = 3 THEN 'numeric_code: cart'
        WHEN behavior_type = 4 THEN 'numeric_code: buy'
        ELSE 'unknown_or_invalid'
    END AS behavior_mapping_status,
    COUNT(*) AS row_count
FROM user_behavior_processed
GROUP BY behavior_type
ORDER BY behavior_type;

SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN time GLOB '????-??-?? ??' THEN 1 ELSE 0 END) AS formatted_hour_time_rows,
    SUM(CASE WHEN time GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]*' THEN 1 ELSE 0 END) AS numeric_timestamp_like_rows,
    SUM(CASE WHEN LENGTH(CAST(time AS TEXT)) = 13 THEN 1 ELSE 0 END) AS length_13_rows,
    SUM(CASE WHEN LENGTH(CAST(time AS TEXT)) = 10 THEN 1 ELSE 0 END) AS length_10_rows
FROM user_behavior_processed;

SELECT
    SUM(CASE WHEN name IN ('date', 'behavior_date', 'day') THEN 1 ELSE 0 END) AS has_date_column,
    SUM(CASE WHEN name IN ('hour', 'behavior_hour') THEN 1 ELSE 0 END) AS has_hour_column,
    SUM(CASE WHEN name IN ('weekday', 'week_day', 'day_of_week') THEN 1 ELSE 0 END) AS has_weekday_column,
    SUM(CASE WHEN name IN ('behavior_name', 'behavior_label') THEN 1 ELSE 0 END) AS has_behavior_name_column,
    SUM(CASE WHEN name IN ('category_id') THEN 1 ELSE 0 END) AS has_category_id_column
FROM pragma_table_info('user_behavior_processed');

SELECT
    time,
    typeof(time) AS time_sqlite_type,
    user_id,
    item_id,
    item_category,
    behavior_type,
    typeof(behavior_type) AS behavior_type_sqlite_type
FROM user_behavior_processed
LIMIT 30;

SELECT
    CASE
        WHEN
            (
                SELECT SUM(CASE WHEN time GLOB '????-??-?? ??' THEN 1 ELSE 0 END)
                FROM user_behavior_processed
            ) > 0
            AND
            (
                SELECT SUM(CASE WHEN name IN ('behavior_name', 'behavior_label') THEN 1 ELSE 0 END)
                FROM pragma_table_info('user_behavior_processed')
            ) = 0
            AND
            (
                SELECT SUM(CASE WHEN name IN ('date', 'behavior_date', 'hour', 'behavior_hour', 'weekday', 'week_day', 'day_of_week') THEN 1 ELSE 0 END)
                FROM pragma_table_info('user_behavior_processed')
            ) = 0
        THEN '该表不是完全原始raw表；time字段已经被处理为YYYY-MM-DD HH格式。但它也不是最终clean表，因为behavior_type仍是1/2/3/4编码，且没有日期、小时、星期、行为名称等加工字段。建议作为阶段一输入表重新做项目口径下的清洗和映射。'

        WHEN
            (
                SELECT SUM(CASE WHEN time GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]*' THEN 1 ELSE 0 END)
                FROM user_behavior_processed
            ) > 0
        THEN '该表更接近raw表；time字段仍类似原始数字时间戳。'

        ELSE '该表状态不明确，需要结合字段说明和原始文件来源继续确认。'
    END AS data_status_judgement;
