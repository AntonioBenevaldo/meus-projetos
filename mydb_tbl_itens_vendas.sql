-- MySQL dump 10.13  Distrib 8.0.43, for Win64 (x86_64)
--
-- Host: localhost    Database: mydb
-- ------------------------------------------------------
-- Server version	8.0.43

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `tbl_itens_vendas`
--

DROP TABLE IF EXISTS `tbl_itens_vendas`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tbl_itens_vendas` (
  `iad` int NOT NULL AUTO_INCREMENT,
  `cod_ista` varchar(45) NOT NULL,
  `cod_produto` varchar(45) NOT NULL,
  `numero_pedido` varchar(45) NOT NULL,
  `quantidade` varchar(45) NOT NULL,
  `valor` varchar(45) NOT NULL,
  `id_vendas` int NOT NULL,
  `id_produto` int NOT NULL,
  PRIMARY KEY (`iad`),
  UNIQUE KEY `iad_UNIQUE` (`iad`),
  KEY `fk_tbl_itens_vendas_tbl_vendas1_idx` (`id_vendas`),
  KEY `fk_tbl_itens_vendas_tbl_produto1_idx` (`id_produto`),
  CONSTRAINT `fk_tbl_itens_vendas_tbl_produto1` FOREIGN KEY (`id_produto`) REFERENCES `tbl_produto` (`id`),
  CONSTRAINT `fk_tbl_itens_vendas_tbl_vendas1` FOREIGN KEY (`id_vendas`) REFERENCES `tbl_vendas` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tbl_itens_vendas`
--

LOCK TABLES `tbl_itens_vendas` WRITE;
/*!40000 ALTER TABLE `tbl_itens_vendas` DISABLE KEYS */;
/*!40000 ALTER TABLE `tbl_itens_vendas` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-11-02 15:45:04
