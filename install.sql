-- Tables pour Weazel News

CREATE TABLE IF NOT EXISTS `rp_articles` (
  `id` int NOT NULL AUTO_INCREMENT,
  `title` varchar(255) NOT NULL,
  `content` text NOT NULL,
  `author` varchar(100) DEFAULT NULL,
  `image` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `status` varchar(20) DEFAULT 'published',
  `category` varchar(50) DEFAULT 'breaking',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `article_likes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `article_id` int NOT NULL,
  `citizenid` varchar(50) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_like` (`article_id`,`citizenid`),
  KEY `article_id` (`article_id`),
  KEY `citizenid` (`citizenid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `article_comments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `article_id` int NOT NULL,
  `citizenid` varchar(50) NOT NULL,
  `author_name` varchar(100) NOT NULL,
  `comment` text NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `article_id` (`article_id`),
  KEY `citizenid` (`citizenid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `rp_dossiers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `citizenid` varchar(50) NOT NULL,
  `type` varchar(50) NOT NULL DEFAULT 'general',
  `title` varchar(255) NOT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'open',
  `visibility` enum('private','institution','public') NOT NULL DEFAULT 'institution',
  `source_event_id` int DEFAULT NULL,
  `created_by` varchar(50) NOT NULL,
  `created_job` varchar(50) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `closed_at` timestamp NULL DEFAULT NULL,
  `archived` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `idx_citizenid` (`citizenid`),
  KEY `idx_event` (`source_event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `rp_dossier_entries` (
  `id` int NOT NULL AUTO_INCREMENT,
  `dossier_id` int NOT NULL,
  `author` varchar(50) NOT NULL,
  `author_job` varchar(50) NOT NULL,
  `content` text NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `entry_type` varchar(50) NOT NULL,
  `image_path` varchar(255) DEFAULT NULL,
  `caption` text,
  `status` enum('rumour','confirmed','denied') NOT NULL DEFAULT 'rumour',
  `source` varchar(100) DEFAULT 'source anonyme',
  `visibility` enum('public','police') NOT NULL DEFAULT 'public',
  `escalated` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `idx_dossier` (`dossier_id`),
  CONSTRAINT `fk_dossier` FOREIGN KEY (`dossier_id`) REFERENCES `rp_dossiers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;