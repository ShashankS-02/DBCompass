const mongoose = require("mongoose");

const productSchema = new mongoose.Schema({
  sku: { type: String, unique: true },
  name: String,
  attributes: mongoose.Schema.Types.Mixed,
  category: { type: mongoose.Schema.Types.ObjectId, ref: "Category" },
  price: Number,
});
productSchema.index({ name: "text", description: "text" });

module.exports = mongoose.model("Product", productSchema);
