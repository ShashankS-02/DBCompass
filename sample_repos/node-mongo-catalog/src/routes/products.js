const express = require("express");
const Product = require("../models/product");
const router = express.Router();

router.get("/:id", async (req, res) => res.json(await Product.findById(req.params.id)));

router.get("/", async (req, res) => {
  const results = await Product.find({ $text: { $search: req.query.q } }).limit(20);
  res.json(results);
});

router.get("/stats/by-category", async (req, res) => {
  res.json(await Product.aggregate([{ $group: { _id: "$category", count: { $sum: 1 } } }]));
});

module.exports = router;
