// src/pages/Products.jsx
import { useEffect, useState, useContext } from 'react';
import { motion } from 'framer-motion';
import styled from 'styled-components';
import AuthContext from '../context/AuthContext';
import { FaSearch, FaShoppingCart, FaArrowRight, FaFilter, FaTimes, FaCheckCircle, FaExclamationTriangle } from 'react-icons/fa';
import { toast } from "react-hot-toast";
import { Link } from 'react-router-dom';
import { SkeletonProductCard } from '../components/SkeletonLoader';
import AppLayout from '../components/AppLayout';
import { PageHeader, GlowingPageContainer } from '../styles/SharedPageStyles';
import { formatINR } from '../utils/currency';

const Products = () => {
  const { axiosInstance, user } = useContext(AuthContext);
  
  // Core Data States
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [quantities, setQuantities] = useState({});
  const [isLoading, setIsLoading] = useState(true);

  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Core Filters
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [sort, setSort] = useState('');

  // UI Slider State 
  const [highestPrice, setHighestPrice] = useState(1000);
  const [minPrice, setMinPrice] = useState(0);
  const [maxPrice, setMaxPrice] = useState(1000);
  const [inStockOnly, setInStockOnly] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  // Debounced Engine State
  const [debouncedMin, setDebouncedMin] = useState(0);
  const [debouncedMax, setDebouncedMax] = useState(1000);

  // Optimized Debounce for Price Sliders
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedMin(minPrice);
      setDebouncedMax(maxPrice);
      setCurrentPage(1); 
    }, 500);
    return () => clearTimeout(timer);
  }, [minPrice, maxPrice]);

  // Explicit Filter Handlers
  const handleSearchChange = (e) => {
    setSearch(e.target.value);
    setCurrentPage(1);
  };

  const handleCategoryChange = (e) => {
    setCategory(e.target.value);
    setCurrentPage(1);
  };

  const handleSortChange = (e) => {
    setSort(e.target.value);
    setCurrentPage(1);
  };

  const handleStockToggle = (e) => {
    setInStockOnly(e.target.checked);
    setCurrentPage(1);
  };

  const clearFilters = () => {
    setSearch(''); 
    setCategory(''); 
    setSort(''); 
    setMinPrice(0); 
    setMaxPrice(highestPrice); 
    setInStockOnly(false);
    setCurrentPage(1);
  };

  // Safe Fetch Engine with Fallbacks
  useEffect(() => {
    const fetchCatalog = async () => {
      setIsLoading(true);
      try {
        const params = new URLSearchParams({ page: currentPage });
        if (search) params.append('search', search);
        if (category) params.append('category', category);
        if (sort === 'price_asc') params.append('ordering', 'price');
        if (sort === 'price_desc') params.append('ordering', '-price');
        if (debouncedMin > 0) params.append('price__gte', debouncedMin);
        if (debouncedMax < highestPrice) params.append('price__lte', debouncedMax);
        if (inStockOnly) params.append('in_stock', 'true');

        const res = await axiosInstance.get(`/api/products/?${params.toString()}`);
        const items = res.data.results || res.data;
        const validItems = Array.isArray(items) ? items : [];

        if (res.data.count !== undefined) {
          setTotalPages(Math.ceil(res.data.count / 12) || 1);
        }

        // Hydrate detailed data safely
        const productsData = await Promise.all(validItems.map(async p => {
          if (!p || !p.id) return null;
          try {
            const { data } = await axiosInstance.get(`/api/products/${p.id}/`);
            return { 
              ...p, 
              price: Number(p.price || data.price || 0), 
              image: data.image_url || data.image || p.image_url || p.image || null, 
              stock: Number(data.stock !== undefined ? data.stock : (p.stock || 0))
            };
          } catch (e) {
            return { 
              ...p, 
              price: Number(p.price || 0), 
              image: p.image_url || p.image || null, 
              stock: Number(p.stock || 0) 
            };
          }
        }));

        const finalProducts = productsData.filter(Boolean);

        if (isInitialLoad && finalProducts.length > 0) {
          const calculatedMax = Math.ceil(Math.max(...finalProducts.map(p => Number(p.price || 0))));
          setHighestPrice(calculatedMax);
          setMaxPrice(calculatedMax);
          setDebouncedMax(calculatedMax);
          setIsInitialLoad(false);
        }

        setProducts(finalProducts);

        const initialQuantities = {};
        finalProducts.forEach(p => initialQuantities[p.id] = 1);
        setQuantities(initialQuantities);

      } catch (err) {
        console.error("Failed to load products:", err);
        toast.error("❌ Failed to load catalog.");
      } finally {
        setIsLoading(false);
      }
    };

    fetchCatalog();

    axiosInstance.get('/api/categories/')
      .then(res => setCategories(res.data.results || res.data))
      .catch(() => console.warn('Failed to load categories'));
      
    // eslint-disable-next-line
  }, [axiosInstance, currentPage, search, category, sort, debouncedMin, debouncedMax, inStockOnly]);

  const filtersActive = search || category || sort || minPrice > 0 || maxPrice < highestPrice || inStockOnly;

  const addToCart = async (product) => {
    const qty = quantities[product.id] || 1;
    if (qty > product.stock) return toast.error(`Only ${product.stock} in stock!`);

    if (user) {
      try {
        await axiosInstance.post('/api/cart-items/', { product: product.id, quantity: qty });
        toast.success(t => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span>🛒 <b>{product.name}</b> added to cart!</span>
            <Link to="/cart/" onClick={() => toast.dismiss(t.id)} style={{ color: '#0B8457', fontWeight: 'bold', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.9rem', marginTop: '4px' }}>
              Go to Cart <FaArrowRight size={12} />
            </Link>
          </div>
        ));
      } catch (err) {
        const msg = err.response?.data?.non_field_errors?.[0] || err.response?.data?.detail || '';
        if (msg.toLowerCase().includes('already')) toast.error(`⚠️ ${product.name} is already in your cart.`);
        else toast.error(`❌ Failed to add to cart.`);
      }
    } else {
      let tempCart = JSON.parse(localStorage.getItem('tempCart')) || [];
      const existing = tempCart.find(item => String(item.product) === String(product.id));
      if (existing) {
        if (existing.quantity + qty > product.stock) return toast.error(`Cannot exceed stock limit`);
        existing.quantity += qty;
      } else {
        tempCart.push({ id: `temp_${product.id}`, product: product.id, product_name: product.name, product_image: product.image, price: product.price, quantity: qty, product_stock: product.stock });
      }
      localStorage.setItem('tempCart', JSON.stringify(tempCart));
      toast.success(t => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span>🛒 <b>{product.name}</b> added to guest cart!</span>
          <Link to="/cart/" onClick={() => toast.dismiss(t.id)} style={{ color: '#0B8457', fontWeight: 'bold', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.9rem', marginTop: '4px' }}>Go to Cart <FaArrowRight size={12} /></Link>
        </div>
      ));
    }
  };

  return (
    <AppLayout>
      <GlowingPageContainer $maxWidth="1100px">
        <PageHeader
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        >
          <BadgeTag>Explore Catalog</BadgeTag>
          <h1>Curated Collection</h1>
          <p>Discover hand-picked premium items crafted for performance and elegance.</p>
        </PageHeader>

        <GlassControlHub>
          <FilterRow>
            <SearchBar>
              <FaSearch className="icon" />
              <input type="text" placeholder="Search by name, brand, or feature..." value={search} onChange={handleSearchChange} />
            </SearchBar>
            <Select value={category} onChange={handleCategoryChange}>
              <option value="">All Categories</option>
              {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select value={sort} onChange={handleSortChange}>
              <option value="">Sort By</option>
              <option value="price_asc">Price: Low to High</option>
              <option value="price_desc">Price: High to Low</option>
            </Select>
            <AdvancedToggle onClick={() => setShowFilters(!showFilters)} $active={showFilters}>
              <FaFilter /> Filters
            </AdvancedToggle>
          </FilterRow>

          {showFilters && (
            <AdvancedFilterPanel
              initial={{ opacity: 0, height: 0, marginTop: 0 }}
              animate={{ opacity: 1, height: 'auto', marginTop: '1.25rem' }}
              exit={{ opacity: 0, height: 0, marginTop: 0 }}
            >
              <FilterGrid>
                <PriceSliderContainer>
                  <label>Max Budget</label>
                  <SliderTrack>
                    <TrackFill $min={(minPrice / highestPrice) * 100} $max={(maxPrice / highestPrice) * 100} />
                    <ThumbInput type="range" min="0" max={highestPrice} value={minPrice} onChange={(e) => setMinPrice(Math.min(Number(e.target.value), maxPrice - 1))} style={{ zIndex: minPrice > highestPrice * 0.9 ? 5 : 3 }} />
                    <ThumbInput type="range" min="0" max={highestPrice} value={maxPrice} onChange={(e) => setMaxPrice(Math.max(Number(e.target.value), minPrice + 1))} />
                  </SliderTrack>
                  <PriceLabel>₹{minPrice} - ₹{maxPrice}</PriceLabel>
                </PriceSliderContainer>

                <ToggleSwitch>
                  <input type="checkbox" id="stockToggle" checked={inStockOnly} onChange={handleStockToggle} />
                  <label htmlFor="stockToggle">In Stock Only</label>
                </ToggleSwitch>

                <ClearButton
                  onClick={clearFilters}
                  $visible={filtersActive}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <FaTimes /> Clear All
                </ClearButton>
              </FilterGrid>
            </AdvancedFilterPanel>
          )}
        </GlassControlHub>

        <ProductsContainer>
          {isLoading ? (
            <ProductGrid>
              {[...Array(8)].map((_, index) => <SkeletonProductCard key={index} />)}
            </ProductGrid>
          ) : products.length === 0 ? (
            <EmptyState>
              <span className="emoji">🔍</span>
              <h3>No Products Matching Criteria</h3>
              <p>We couldn't find anything matching your current search or filters.</p>
              {filtersActive && (
                <button className="reset-btn" onClick={clearFilters}>Reset All Filters</button>
              )}
            </EmptyState>
          ) : (
            <ProductGrid>
              {products.map((product) => {
                const qty = quantities[product.id] || 1;
                const stockVal = Number(product.stock || 0);
                const isAtLimit = qty >= stockVal;
                const safePrice = Number(product.price || 0);

                return (
                  <ProductCard
                    key={product.id}
                    as={motion.div}
                    whileHover={{ y: -8 }}
                  >
                    {product.image && (
                      <ProductImage>
                        <StockBadge $stock={stockVal}>
                          {stockVal > 5 ? (
                            <><FaCheckCircle size={10} /> In Stock</>
                          ) : stockVal > 0 ? (
                            <><FaExclamationTriangle size={10} /> Low Stock ({stockVal})</>
                          ) : (
                            <>Out of Stock</>
                          )}
                        </StockBadge>

                        <Link to={`/products/${product.id}/`}>
                          <img src={product.image} alt={product.name || 'Product'} />
                        </Link>
                      </ProductImage>
                    )}
                    <ProductInfo>
                      <div className="meta">
                        <Link to={`/products/${product.id}/`} className="title">{product.name || 'Untitled Product'}</Link>
                        <p className="desc">{String(product.description || '').slice(0, 65)}...</p>
                      </div>

                      <PriceRow>
                        <Price>{formatINR(safePrice)}</Price>

                        <QuantityControl>
                          <button onClick={() => setQuantities(prev => ({ ...prev, [product.id]: Math.max(1, (prev[product.id] || 1) - 1) }))} disabled={qty <= 1}>-</button>
                          <span>{qty}</span>
                          <button disabled={isAtLimit} onClick={() => setQuantities(prev => ({ ...prev, [product.id]: Math.min(stockVal, (prev[product.id] || 1) + 1) }))} style={{ opacity: isAtLimit ? 0.4 : 1, cursor: isAtLimit ? 'not-allowed' : 'pointer' }}>+</button>
                        </QuantityControl>
                      </PriceRow>

                      <AddToCartButton
                        onClick={() => addToCart(product)}
                        disabled={stockVal === 0}
                        whileTap={{ scale: 0.96 }}
                        $outOfStock={stockVal === 0}
                      >
                        <FaShoppingCart /> {stockVal === 0 ? 'Out of Stock' : 'Add to Cart'}
                      </AddToCartButton>
                    </ProductInfo>
                  </ProductCard>
                );
              })}
            </ProductGrid>
          )}

          {totalPages > 1 && (
            <PaginationWrapper>
              <PageButton onClick={() => setCurrentPage(p => Math.max(p - 1, 1))} disabled={currentPage === 1}>&larr; Prev</PageButton>
              <PageInfo>Page {currentPage} of {totalPages}</PageInfo>
              <PageButton onClick={() => setCurrentPage(p => Math.min(p + 1, totalPages))} disabled={currentPage === totalPages}>Next &rarr;</PageButton>
            </PaginationWrapper>
          )}
        </ProductsContainer>
      </GlowingPageContainer>
    </AppLayout>
  );
};

export default Products;

// ==========================================
// PAGE SPECIFIC STYLED COMPONENTS (RESPONSIVE OPTIMIZED)
// ==========================================

const BadgeTag = styled.span`
  display: inline-block;
  background: rgba(11, 132, 87, 0.1);
  color: #0B8457;
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.3rem 0.9rem;
  border-radius: 50px;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 0.8rem;
  border: 1px solid rgba(11, 132, 87, 0.2);
`;

const GlassControlHub = styled.div`
  position: sticky;
  top: 86px;
  z-index: 50;
  max-width: 1250px;
  margin: 0 auto 2.5rem auto;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 1);
  border-radius: 24px;
  padding: 1.1rem 1.5rem;
  box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.05), 0 0 0 1px rgba(0, 0, 0, 0.03);
  width: 92%;
  box-sizing: border-box;

  @media (max-width: 768px) {
    padding: 1rem;
    width: 95%;
    margin-bottom: 1.5rem;
    top: 76px;
  }
`;

const FilterRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;

  @media (max-width: 768px) {
    gap: 0.75rem;
  }
`;

const SearchBar = styled.div`
  display: flex;
  align-items: center;
  background: #ffffff;
  padding: 0.7rem 1.2rem;
  border-radius: 50px;
  border: 1px solid #E5E7EB;
  flex: 2;
  min-width: 260px;
  transition: all 0.2s ease;
  box-sizing: border-box;

  &:focus-within {
    border-color: #0B8457;
    box-shadow: 0 0 0 4px rgba(11, 132, 87, 0.1);
  }

  input {
    border: none;
    margin-left: 0.6rem;
    font-size: 0.95rem;
    width: 100%;
    color: #111827;
    background: transparent;
    &:focus { outline: none; }
    &::placeholder { color: #9CA3AF; }
  }
  .icon { color: #9CA3AF; font-size: 1.1rem; }

  @media (max-width: 768px) {
    min-width: 100%;
    padding: 0.6rem 1rem;
  }
`;

const Select = styled.select`
  padding: 0.7rem 1.2rem;
  border-radius: 50px;
  border: 1px solid #E5E7EB;
  background: #ffffff;
  font-size: 0.95rem;
  font-weight: 600;
  color: #374151;
  cursor: pointer;
  flex: 1;
  min-width: 160px;
  transition: all 0.2s ease;
  appearance: none;
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236B7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
  background-repeat: no-repeat;
  background-position: right 1rem center;
  background-size: 1em;
  box-sizing: border-box;

  &:focus { outline: none; border-color: #0B8457; box-shadow: 0 0 0 4px rgba(11, 132, 87, 0.1); }

  @media (max-width: 768px) {
    min-width: 48%;
    flex: 1 1 48%;
    padding: 0.6rem 1rem;
    font-size: 0.85rem;
  }
`;

const AdvancedToggle = styled.button`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.7rem 1.5rem;
  border-radius: 50px;
  border: 1px solid ${props => props.$active ? '#0B8457' : '#E5E7EB'};
  background: ${props => props.$active ? '#0B8457' : '#ffffff'};
  color: ${props => props.$active ? '#ffffff' : '#374151'};
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: ${props => props.$active ? '#086341' : '#F9FAFB'};
  }

  @media (max-width: 768px) {
    width: 100%;
    justify-content: center;
    padding: 0.6rem 1rem;
  }
`;

const AdvancedFilterPanel = styled(motion.div)`
  overflow: hidden;
  border-top: 1px solid #E5E7EB;
`;

const FilterGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  padding: 1rem 0 0.5rem 0;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
    gap: 1.25rem;
    padding: 0.75rem 0 0.25rem 0;
  }
`;

const PriceSliderContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 1.5rem;
  flex: 1;
  min-width: 300px;

  label { font-weight: 600; color: #374151; font-size: 0.95rem; }

  @media (max-width: 768px) {
    min-width: 100%;
    flex-direction: column;
    align-items: stretch;
    gap: 0.75rem;
  }
`;

const SliderTrack = styled.div`
  position: relative; height: 6px; background: #E5E7EB; border-radius: 4px; flex: 1; display: flex; align-items: center;
`;
const TrackFill = styled.div`
  position: absolute; height: 100%; background: #0B8457; border-radius: 4px; left: ${props => props.$min}%; right: ${props => 100 - props.$max}%;
`;
const ThumbInput = styled.input`
  position: absolute; width: 100%; -webkit-appearance: none; background: transparent; pointer-events: none; outline: none;
  &::-webkit-slider-thumb { -webkit-appearance: none; pointer-events: auto; width: 20px; height: 20px; background: white; border: 3px solid #0B8457; border-radius: 50%; cursor: pointer; box-shadow: 0 2px 6px rgba(0,0,0,0.15); }
  &::-moz-range-thumb { pointer-events: auto; width: 20px; height: 20px; background: white; border: 3px solid #0B8457; border-radius: 50%; cursor: pointer; box-shadow: 0 2px 6px rgba(0,0,0,0.15); }
`;
const PriceLabel = styled.div`
  font-weight: 700; color: #0B8457; font-size: 0.95rem; min-width: 95px; text-align: right; font-variant-numeric: tabular-nums;

  @media (max-width: 768px) {
    text-align: center;
  }
`;

const ToggleSwitch = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;

  label { font-weight: 600; color: #374151; cursor: pointer; font-size: 0.95rem; }
  input[type="checkbox"] { width: 18px; height: 18px; accent-color: #0B8457; cursor: pointer; }

  @media (max-width: 768px) {
    justify-content: flex-start;
  }
`;

const ClearButton = styled(motion.button)`
  display: flex; 
  align-items: center; 
  justify-content: center;
  gap: 0.4rem; 
  padding: 0.6rem 1.2rem; 
  background: #FEF2F2; 
  color: #DC2626; 
  border: 1px solid #FCA5A5; 
  border-radius: 50px; 
  font-weight: 600; 
  font-size: 0.9rem; 
  cursor: pointer;
  visibility: ${props => props.$visible ? 'visible' : 'hidden'};
  opacity: ${props => props.$visible ? 1 : 0};
  pointer-events: ${props => props.$visible ? 'auto' : 'none'};
  transition: opacity 0.2s ease;

  &:hover { background: #FEE2E2; }

  @media (max-width: 768px) {
    width: 100%;
  }
`;

const ProductsContainer = styled.div`
  position: relative;
  z-index: 1;
  max-width: 1500px; 
  margin: 0 auto;
  padding: 0 2.5rem;
  box-sizing: border-box;

  @media (max-width: 768px) {
    padding: 0 0.75rem;
    margin-top: 1rem; 
  }
`;

const ProductGrid = styled.div`
  display: grid;
  gap: 2rem;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));

  @media (max-width: 768px) {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 1rem;
  }
`;

const ProductCard = styled(motion.div)`
  background: #ffffff;
  border-radius: 24px;
  padding: 1.2rem;
  border: 1px solid rgba(11, 132, 87, 0.12);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
  height: 100%;
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
  box-sizing: border-box;

  &:hover {
    border-color: rgba(11, 132, 87, 0.4);
    box-shadow: 0 20px 40px -10px rgba(11, 132, 87, 0.15);
  }

  @media (max-width: 768px) {
    padding: 0.85rem;
    border-radius: 18px;
    margin-bottom: 0;
  }
`;

const ProductImage = styled.div`
  width: 100%;
  aspect-ratio: 1 / 1;
  background: #FFFFFF;
  border-radius: 16px;
  margin-bottom: 1.25rem;
  position: relative;
  overflow: hidden;
  border: 1px solid #F1F5F9;

  a {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    padding: 1.5rem;
    box-sizing: border-box;
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
    transition: transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
    mix-blend-mode: multiply;
  }

  &:hover img {
    transform: scale(1.12);
  }

  @media (max-width: 768px) {
    margin-bottom: 0.85rem;
    border-radius: 12px;
    a { padding: 1rem; }
  }
`;

const StockBadge = styled.div`
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.3rem 0.7rem;
  border-radius: 50px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);

  background: ${props =>
    props.$stock > 5 ? 'rgba(236, 253, 245, 0.9)' :
    props.$stock > 0 ? 'rgba(254, 243, 199, 0.9)' :
    'rgba(254, 226, 226, 0.9)'};

  color: ${props =>
    props.$stock > 5 ? '#047857' :
    props.$stock > 0 ? '#B45309' :
    '#B91C1C'};

  border: 1px solid ${props =>
    props.$stock > 5 ? 'rgba(16, 185, 129, 0.3)' :
    props.$stock > 0 ? 'rgba(245, 158, 11, 0.3)' :
    'rgba(239, 68, 68, 0.3)'};

  @media (max-width: 768px) {
    font-size: 0.65rem;
    padding: 0.2rem 0.5rem;
    top: 8px;
    left: 8px;
  }
`;

const ProductInfo = styled.div`
  display: flex;
  flex-direction: column;
  flex-grow: 1;

  .meta {
    flex-grow: 1;
    margin-bottom: 1.2rem;
  }

  .title {
    font-size: 1.15rem;
    font-weight: 800;
    color: #111827;
    text-decoration: none;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    margin-bottom: 0.5rem;
    transition: color 0.2s;

    &:hover { color: #0B8457; }
  }

  .desc {
    color: #6B7280;
    font-size: 0.88rem;
    line-height: 1.5;
  }

  @media (max-width: 768px) {
    .meta { margin-bottom: 0.8rem; }
    .title { font-size: 0.95rem; margin-bottom: 0.3rem; }
    .desc { display: none; } /* Hide long description on tight mobile grids for clean UI */
  }
`;

const PriceRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.2rem;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
    margin-bottom: 0.8rem;
  }
`;

const Price = styled.div`
  font-size: 1.45rem;
  font-weight: 900;
  color: #0F172A;
  letter-spacing: -0.5px;

  @media (max-width: 768px) {
    font-size: 1.15rem;
  }
`;

const QuantityControl = styled.div`
  display: flex;
  align-items: center;
  background: #F8FAFC;
  border-radius: 50px;
  padding: 0.25rem;
  border: 1px solid #E2E8F0;

  button {
    background: #ffffff;
    color: #334155;
    border: none;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    cursor: pointer;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    transition: all 0.2s ease;

    &:hover:not(:disabled) {
      background: #0B8457;
      color: white;
    }
  }

  span {
    min-width: 30px;
    text-align: center;
    font-size: 0.9rem;
    font-weight: 700;
    color: #0F172A;
  }

  @media (max-width: 768px) {
    width: 100%;
    justify-content: space-between;
  }
`;

const AddToCartButton = styled(motion.button)`
  width: 100%;
  padding: 0.9rem;
  background: ${props => props.$outOfStock ? '#F1F5F9' : 'linear-gradient(135deg, #0B8457 0%, #075E3E 100%)'};
  color: ${props => props.$outOfStock ? '#94A3B8' : '#ffffff'};
  border: none;
  border-radius: 14px;
  font-weight: 700;
  font-size: 0.95rem;
  cursor: ${props => props.$outOfStock ? 'not-allowed' : 'pointer'};
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  position: relative;
  overflow: hidden;
  box-shadow: ${props => props.$outOfStock ? 'none' : '0 4px 14px rgba(11, 132, 87, 0.25)'};
  transition: all 0.3s ease;

  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: -150%;
    width: 50%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.25), transparent);
    transform: skewX(-25deg);
    animation: ${props => props.$outOfStock ? 'none' : 'shimmer 4s infinite'};
  }

  @keyframes shimmer {
    0% { left: -150%; }
    20% { left: 200%; }
    100% { left: 200%; }
  }

  &:hover:not(:disabled) {
    box-shadow: 0 6px 20px rgba(11, 132, 87, 0.4);
  }

  @media (max-width: 768px) {
    padding: 0.75rem;
    font-size: 0.85rem;
    border-radius: 10px;
  }
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 5rem 2rem;
  background: #ffffff;
  border-radius: 24px;
  border: 1px dashed #E2E8F0;
  max-width: 600px;
  margin: 0 auto;

  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; margin-bottom: 1.5rem; }

  .reset-btn {
    background: #0B8457;
    color: white;
    border: none;
    padding: 0.8rem 1.8rem;
    border-radius: 50px;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.2s;

    &:hover { background: #086341; }
  }

  @media (max-width: 768px) {
    padding: 3rem 1rem;
  }
`;

const PaginationWrapper = styled.div`
  display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 4rem;

  @media (max-width: 768px) {
    margin-top: 2.5rem;
    gap: 0.5rem;
  }
`;

const PageButton = styled.button`
  padding: 0.7rem 1.6rem;
  border-radius: 50px;
  border: none;
  font-weight: 700;
  background: ${props => props.disabled ? '#F1F5F9' : '#0B8457'};
  color: ${props => props.disabled ? '#94A3B8' : 'white'};
  cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'};
  transition: all 0.2s ease;
  box-shadow: ${props => props.disabled ? 'none' : '0 4px 12px rgba(11, 132, 87, 0.25)'};

  &:hover:not(:disabled) {
    background: #086341;
    transform: translateY(-2px);
  }

  @media (max-width: 768px) {
    padding: 0.5rem 1rem;
    font-size: 0.85rem;
  }
`;

const PageInfo = styled.span`
  font-weight: 700; color: #334155; font-size: 0.95rem;

  @media (max-width: 768px) {
    font-size: 0.85rem;
  }
`;