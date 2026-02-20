-- Databricks notebook source
-- Demo Scaffold — Schema Setup
-- Run this first to create the catalog schema.

-- COMMAND ----------

-- TODO: Replace with your catalog name
USE CATALOG TODO_CATALOG;

-- COMMAND ----------

-- TODO: Replace with your schema name and add a meaningful comment
CREATE SCHEMA IF NOT EXISTS TODO_SCHEMA
COMMENT 'TODO: Describe your demo domain here';

-- COMMAND ----------

USE SCHEMA TODO_SCHEMA;

-- COMMAND ----------

-- Verify schema is ready
SELECT current_catalog(), current_schema();
