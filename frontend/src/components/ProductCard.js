import React from 'react';

const ProductCard = ({ product, quantity, setQuantity, addToCart }) => {
  return (
    <div className="bg-white shadow-md rounded-lg p-4 flex flex-col items-center max-w-xs">
      {/* Nuclear Option: Strictly constrained container + inline styles */}
      <div 
        className="flex-none w-8 h-8 mb-3"  // Disables flex stretching
        style={{ minWidth: '32px', minHeight: '32px' }}  // Prevents collapse
      >
        <img
          src={product.image_url}
          alt={product.name}
          className="block w-full h-full object-contain"  // Block display prevents inline gaps
          style={{
            maxWidth: '100%',
            maxHeight: '100%',
            objectFit: 'contain',  // Overrides any global CSS
          }}
        />
      </div>

      {/* Rest of the card */}
      <h2 className="text-lg font-semibold text-center mb-2">{product.name}</h2>
      <p className="text-sm text-gray-600 text-center mb-2">{product.description}</p>
      <p className="text-md font-bold text-center mb-1">₹{product.price}</p>
      <p className="text-xs text-gray-500 mb-4">Stock: {product.stock}</p>

      <div className="flex items-center space-x-2">
        <input
          type="number"
          min="1"
          max={product.stock}
          value={quantity}
          onChange={e => setQuantity(parseInt(e.target.value))}
          className="border rounded px-2 py-1 w-16 text-sm"
        />
        <button
          onClick={addToCart}
          className="bg-blue-600 text-white text-sm px-3 py-1.5 rounded hover:bg-blue-700 transition"
        >
          Add to Cart
        </button>
      </div>
    </div>
  );
};

export default ProductCard;