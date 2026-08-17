DROP VIEW IF EXISTS vw_user_behavior_mapped;

CREATE VIEW vw_user_behavior_mapped AS
SELECT
    time,
    SUBSTR(time, 1, 10) AS behavior_date,
    SUBSTR(time, 12, 2) AS behavior_hour,
    user_id,
    item_id,
    item_category AS category_id,
    behavior_type,
    CASE
        WHEN behavior_type = 1 THEN 'pv'
        WHEN behavior_type = 2 THEN 'fav'
        WHEN behavior_type = 3 THEN 'cart'
        WHEN behavior_type = 4 THEN 'buy'
        ELSE 'unknown'
    END AS behavior_name
FROM user_behavior_processed;
