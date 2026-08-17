CREATE INDEX IF NOT EXISTS idx_ub_time
ON user_behavior_processed(time);

CREATE INDEX IF NOT EXISTS idx_ub_user_id
ON user_behavior_processed(user_id);

CREATE INDEX IF NOT EXISTS idx_ub_item_id
ON user_behavior_processed(item_id);

CREATE INDEX IF NOT EXISTS idx_ub_item_category
ON user_behavior_processed(item_category);

CREATE INDEX IF NOT EXISTS idx_ub_behavior_type
ON user_behavior_processed(behavior_type);

ANALYZE;
