const mongoose = require("mongoose");

const reviewSchema = new mongoose.Schema({
  product: { type: mongoose.Schema.Types.ObjectId, ref: "Product" },
  rating: Number,
  body: String,
});

module.exports = mongoose.model("Review", reviewSchema);
