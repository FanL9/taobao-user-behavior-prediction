-- 基础EDA
-- 1
-- 统计四类行为分布：
   -- 浏览 `pv`；
   -- 收藏 `fav`；
   -- 加购 `cart`；
   -- 购买 `buy`。
-- behavior_distribution.csv
SELECT
    behavior_name,
    COUNT(*) AS behavior_count,
    ROUND(
        COUNT(*) * 100.0 /
        (SELECT COUNT(*)
         FROM `user_behavior_clean`
         WHERE behavior_name IN ('pv', 'fav', 'cart', 'buy')),
        2
    ) AS percentage
FROM `user_behavior_clean`
WHERE behavior_name IN ('pv', 'fav', 'cart', 'buy')
GROUP BY behavior_name
ORDER BY behavior_count DESC;



-- 2
-- 用户行为次数；
   -- 用户购买次数；
   -- 购买用户数；
   -- 未购买用户数；
   -- 复购用户数。
-- 购买用户：只要有≥1 条 buy 行为就算；
-- 未购买用户：有浏览 / 收藏 / 加购行为，但完全没有 buy 记录；
-- 复购用户：同一个 user_id，购买行为≥2 次（按行为记录，不是按订单）。
-- behavior_statistics.csv
SELECT
    COUNT(*) AS total_behavior_count,
    SUM(CASE WHEN behavior_name = 'buy' THEN 1 ELSE 0 END) AS total_purchase_count,
    COUNT(DISTINCT CASE WHEN behavior_name = 'buy' THEN user_id END) AS purchase_users,
    COUNT(DISTINCT user_id) - COUNT(DISTINCT CASE WHEN behavior_name = 'buy' THEN user_id END) AS non_purchase_users,
    COUNT(DISTINCT CASE
        WHEN user_id IN (
            SELECT user_id
            FROM user_behavior_clean
            WHERE behavior_name = 'buy'
            GROUP BY user_id
            HAVING COUNT(*) >= 2
        )
        THEN user_id
    END) AS repeat_purchase_users
FROM user_behavior_clean;



-- 3
-- 统计商品行为：
   -- 商品浏览次数；
   -- 商品收藏次数；
   -- 商品加购次数；
   -- 商品购买次数；
   -- 热门商品。
-- item_statistics.csv
SELECT
    item_id,
    SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS pv_count,
    SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS fav_count,
    SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS cart_count,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy_count
FROM user_behavior_clean
GROUP BY item_id;
-- 热门商品 = 按购买次数 buy_count 排名前 10 的商品。
-- top_10_item.csv
SELECT
    item_id,
    pv_count,
    fav_count,
    cart_count,
    buy_count
FROM item_statistics
ORDER BY buy_count DESC
LIMIT 10;



-- 4
-- 统计类目行为：
   -- 类目行为总量；
   -- 类目购买量；
   -- 热门类目；
   -- 类目购买占比。
-- category_statistics.csv
SELECT
    category_id,
    COUNT(*) AS total_behavior_count,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS buy_count,
    ROUND(
        SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) * 100.0 /
        SUM(SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END)) OVER (),
        2
    ) AS buy_percentage
FROM user_behavior_clean
GROUP BY category_id
ORDER BY buy_count DESC;
-- 热门类目= 按购买次数 buy_count 排名前 10 的类目。
-- top_10_category.csv
SELECT
    category_id,
    total_behavior_count,
    buy_count,
    buy_percentage
FROM category_statistics
ORDER BY buy_count DESC, category_id
LIMIT 10;



-- 5
-- 统计时间分布：
   -- 日期维度行为量；
   -- 小时维度行为量；
   -- 不同行为类型的时间分布。
-- daily_behavior.csv
SELECT
    behavior_date,
    COUNT(*) AS behavior_count
FROM user_behavior_clean
GROUP BY behavior_date
ORDER BY behavior_date;
-- hourly_behavior.csv
SELECT
    behavior_hour,
    COUNT(*) AS behavior_count
FROM user_behavior_clean
GROUP BY behavior_hour
ORDER BY behavior_hour;
-- behavior_hourly_distribution.csv
SELECT
    behavior_hour,
    SUM(CASE WHEN behavior_name = 'pv' THEN 1 ELSE 0 END) AS pv_count,
    SUM(CASE WHEN behavior_name = 'fav' THEN 1 ELSE 0 END) AS fav_count,
    SUM(CASE WHEN behavior_name = 'cart' THEN 1 ELSE 0 END) AS cart_count,
    SUM(CASE WHEN behavior_name = 'buy' THEN 1 ELSE 0 END) AS buy_count
FROM user_behavior_clean
GROUP BY behavior_hour
ORDER BY behavior_hour;



-- 6
-- 构建初步转化漏斗：
   -- 浏览；
   -- 收藏；
   -- 加购；
   -- 购买。
-- descriptive_funnel.csv
SELECT
    'PV' AS stage,
    SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END) AS behavior_count,
    100.00 AS relative_to_pv
FROM user_behavior_clean
UNION ALL
SELECT
    'Favorite' AS stage,
    SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) AS behavior_count,
    ROUND(
        SUM(CASE WHEN behavior_type = 2 THEN 1 ELSE 0 END) * 100.0 /
        SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END),
        2
    ) AS relative_to_pv
FROM user_behavior_clean
UNION ALL
SELECT
    'Cart' AS stage,
    SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) AS behavior_count,
    ROUND(
        SUM(CASE WHEN behavior_type = 3 THEN 1 ELSE 0 END) * 100.0 /
        SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END),
        2
    ) AS relative_to_pv
FROM user_behavior_clean
UNION ALL
SELECT
    'Purchase' AS stage,
    SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) AS behavior_count,
    ROUND(
        SUM(CASE WHEN behavior_type = 4 THEN 1 ELSE 0 END) * 100.0 /
        SUM(CASE WHEN behavior_type = 1 THEN 1 ELSE 0 END),
        2
    ) AS relative_to_pv
FROM user_behavior_clean;
