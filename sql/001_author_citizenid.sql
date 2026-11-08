-- Weazel News hotfix migration 001: article ownership by citizenid.
-- ADDITIVE ONLY: adds a nullable column and an index. No data is changed or dropped.
-- Run ONCE on the production database (MySQL 8 has no "ADD COLUMN IF NOT EXISTS"; a second run errors harmlessly).
-- Back up first:  mysqldump qbcore rp_articles > rp_articles_backup.sql
--
-- Existing rows keep author_citizenid = NULL; for those the resource keeps comparing the author's
-- character name (old behaviour). New articles store the citizenid and are checked by it.

ALTER TABLE `rp_articles`
  ADD COLUMN `author_citizenid` varchar(50) NULL DEFAULT NULL AFTER `author`,
  ADD KEY `idx_articles_author_cid` (`author_citizenid`),
  ADD KEY `idx_articles_status_created` (`status`, `created_at`);

-- Verify:
--   SELECT COUNT(*) AS total, SUM(author_citizenid IS NULL) AS legacy_rows FROM rp_articles;
-- Rollback (safe, removes only what this file added):
--   ALTER TABLE `rp_articles` DROP KEY `idx_articles_status_created`, DROP KEY `idx_articles_author_cid`, DROP COLUMN `author_citizenid`;
