-- Realistic legacy data for importer tests. Loaded into a MySQL/MariaDB database that already has install.sql applied.
SET time_zone = '+00:00';
DELETE FROM article_likes; DELETE FROM article_comments; DELETE FROM rp_dossier_entries; DELETE FROM rp_dossiers; DELETE FROM rp_articles;

INSERT INTO rp_articles (id,title,content,author,image,created_at,status,category) VALUES
 (1,'Braquage à Vinewood','Trois suspects ont été arrêtés après un braquage. « Aucun blessé », selon la police. ☕','Jo Journalist','https://cdn.example/img/1.png','2026-01-10 09:30:00','published','crime'),
 (2,'Budget municipal','Le conseil a voté le budget 2026.','Ed Editor',NULL,'2026-01-11 14:00:00','published','politics'),
 (3,'Brouillon en cours','Texte non terminé','Jo Journalist',NULL,'2026-01-12 08:00:00','draft','breaking'),
 (4,'En attente de validation','Prêt pour relecture','Ivy Intern','https://cdn.example/i.png','2026-01-12 10:00:00','pending','events'),
 (5,'Statut inconnu','Ce statut n''existe pas','Ghost Writer',NULL,'2026-01-13 10:00:00','weird','sports'),
 (6,'Image hostile','Corps','Twin Name','javascript:alert(1)','2026-01-13 11:00:00','published','breaking'),
 (7,'Sans auteur','Corps sans auteur',NULL,NULL,'2026-01-14 12:00:00','published',NULL);

INSERT INTO article_comments (id,article_id,citizenid,author_name,comment,created_at) VALUES
 (1,1,'CIT001','Pat Citizen','Super article !','2026-01-10 10:00:00'),
 (2,1,'CIT002','Sam Reader','Merci pour l''info 🙏','2026-01-10 11:00:00'),
 (3,2,'CIT001','Pat Citizen','<script>alert(1)</script>','2026-01-11 15:00:00'),
 (4,99,'CIT003','Orphan','comment on deleted article','2026-01-11 16:00:00');

INSERT INTO article_likes (id,article_id,citizenid,created_at) VALUES
 (1,1,'CIT001','2026-01-10 10:05:00'),(2,1,'CIT002','2026-01-10 11:05:00'),(3,2,'CIT001','2026-01-11 15:05:00'),(4,98,'CIT009','2026-01-11 16:05:00');

INSERT INTO rp_dossiers (id,citizenid,type,title,status,visibility,source_event_id,created_by,created_job,created_at,closed_at,archived) VALUES
 (1,'REP2','general','Corruption au port','open','institution',NULL,'Ed Editor','reporter','2026-01-05 08:00:00',NULL,0),
 (2,'REP1','general','Source sensible','open','private',NULL,'Jo Journalist','reporter','2026-01-06 08:00:00',NULL,0),
 (3,'REP1','general','Ancien dossier','closed','public',NULL,'Jo Journalist','reporter','2026-01-07 08:00:00','2026-01-20 08:00:00',0),
 (4,'REP2','general','Supprimé','open','institution',NULL,'Ed Editor','reporter','2026-01-08 08:00:00',NULL,1),
 (5,'REP2','investigation','Statut étrange','mystery','institution',7,'Ed Editor','reporter','2026-01-09 08:00:00',NULL,0);

INSERT INTO rp_dossier_entries (id,dossier_id,author,author_job,content,created_at,entry_type,image_path,caption,status,source,visibility,escalated) VALUES
 (1,1,'Ed Editor','reporter','Un dock a été vu la nuit','2026-01-05 09:00:00','rumour',NULL,NULL,'rumour','source anonyme','public',0),
 (2,1,'Jo Journalist','reporter','Confirmé par deux témoins','2026-01-05 12:00:00','confirmed','uploads/a.png','Photo du dock','rumour','Témoin A','public',0),
 (3,1,'Ed Editor','reporter','Le maire dément','2026-01-06 12:00:00','denied',NULL,NULL,'rumour','Communiqué','police',1),
 (4,2,'Jo Journalist','reporter','Identité à protéger','2026-01-06 09:00:00','rumour',NULL,NULL,'rumour','source anonyme','public',0),
 (5,3,'Jo Journalist','reporter','Clos','2026-01-07 09:00:00','confirmed',NULL,NULL,'rumour','source anonyme','public',0),
 (6,5,'Ed Editor','reporter','Type inconnu','2026-01-09 09:00:00','speculation',NULL,NULL,'rumour','source anonyme','public',0);
