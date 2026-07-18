-- Dump of acmedb.support_tickets
-- Torchstone Desk export bridge
-- Server version 8.0.34
-- Dump completed on 2026-06-30 02:14:57
--
-- Table structure for table `support_tickets`
--

DROP TABLE IF EXISTS `support_tickets`;
CREATE TABLE `support_tickets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticket_ref` varchar(16) NOT NULL,
  `account_id` varchar(16) DEFAULT NULL,
  `subject` varchar(255) NOT NULL,
  `priority` enum('low','normal','high','urgent') DEFAULT 'normal',
  `status` enum('open','pending','resolved','closed') DEFAULT 'open',
  `assignee` varchar(64) DEFAULT NULL,
  `related_invoice` varchar(20) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `resolved_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ticket_ref` (`ticket_ref`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

--
-- Dumping data for table `support_tickets`
--

INSERT INTO `support_tickets` VALUES
(1,'SUP-1042','ACCT-1001','Ingestion lag - events delayed >5min during peak','urgent','resolved','yuki.tanaka',NULL,'2026-03-11 09:22:00','2026-03-11 15:47:00'),
(2,'SUP-1043','ACCT-1001','API returning 502 on /v1/usage exports','high','resolved','marcus.webb',NULL,'2026-03-11 09:41:00','2026-03-11 16:05:00'),
(3,'SUP-1044','ACCT-1002','Can\'t rotate API key - \"insufficient scope\" error','normal','closed','sam.osei',NULL,'2026-03-19 13:10:00','2026-03-20 08:55:00');

INSERT INTO `support_tickets` VALUES
(4,'SUP-1045','ACCT-1013','Invoice INV-202603-0063 shows wrong seat count','high','pending','carlos.mendes','INV-202603-0063','2026-04-02 11:03:00',NULL),
(5,'SUP-1046',NULL,'How do I export scheduled reports to S3-compatible bucket?','low','resolved','aisha.diallo',NULL,'2026-04-05 16:20:00','2026-04-06 09:12:00'),
(6,'SUP-1047','ACCT-1002','Dashboard shows \"no data\" after timezone change','normal','open','yuki.tanaka',NULL,'2026-04-11 08:47:00',NULL),
(7,'SUP-1048','ACCT-1001','Bluewater feed: duplicate events on re-ingest','high','resolved','elena.sokolova',NULL,'2026-04-18 10:30:00','2026-04-19 14:22:00');

INSERT INTO `support_tickets` VALUES (8,'SUP-1049','ACCT-1005','Requesting SOC 2 report / security questionnaire','normal','pending','ingrid.bauer',NULL,'2026-05-04 09:00:00',NULL);
INSERT INTO `support_tickets` VALUES (9,'SUP-1050','ACCT-1013','Phishing email impersonating \"Acme Billing\" - reported','urgent','closed','omar.haddad',NULL,'2026-05-20 09:18:00','2026-05-20 11:40:00');
INSERT INTO `support_tickets` VALUES (10,'SUP-1051',NULL,'Feature request: per-account rate-limit dashboard','low','open',NULL,NULL,'2026-05-27 15:33:00',NULL);
INSERT INTO `support_tickets` VALUES
(11,'SUP-1052','ACCT-1002','Billing dispute -- charged for churned seats; ref INV-202603-0063','high','pending','carlos.mendes','INV-202603-0063','2026-06-03 12:15:00',NULL),
(12,'SUP-1053','ACCT-1001','VPN (Bramblehold) drops during large export downloads','normal','resolved','diego.fuentes',NULL,'2026-06-09 14:05:00','2026-06-10 10:20:00');
