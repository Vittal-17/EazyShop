// src/pages/ProductDetail.jsx
import { useEffect, useState, useContext } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import styled from 'styled-components';
import AuthContext from '../context/AuthContext';
import { toast } from "react-hot-toast"; 
import { FaStar, FaShoppingCart, FaArrowRight, FaCheckCircle, FaStore, FaExclamationTriangle } from 'react-icons/fa';
import { SkeletonRow } from '../components/SkeletonLoader';
import AppLayout from '../components/AppLayout';
import { GlowingPageContainer } from '../styles/SharedPageStyles';
import { formatINR } from '../utils/currency';

const ProductDetail = () => {
  const { id } = useParams();
  const { axiosInstance, user } = useContext(AuthContext);

  const [product, setProduct] = useState(null);
  const [reviews, setReviews] = useState([]);
  
  const [isLoading, setIsLoading] = useState(true);
  const [reviewsLoading, setReviewsLoading] = useState(true);
  
  const [reviewPage, setReviewPage] = useState(1);
  const [totalReviewPages, setTotalReviewPages] = useState(1);
  const [quantity, setQuantity] = useState(1);
  const [purchaseDate, setPurchaseDate] = useState(null);

  useEffect(() => {
    setIsLoading(true);
    axiosInstance.get(`/api/products/${id}/`)
      .then(res => setProduct(res.data))
      .catch(err => toast.error('❌ Failed to load product.', { duration: 2000 }))
      .finally(() => setIsLoading(false)); 
  }, [id, axiosInstance]);

  const fetchReviews = () => {
    setReviewsLoading(true);
    axiosInstance.get(`/api/reviews/?product=${id}&page=${reviewPage}`)
      .then(res => {
        setReviews(res.data.results || res.data);
        if (res.data.count) setTotalReviewPages(Math.ceil(res.data.count / 12));
      })
      .catch(err => console.error(err))
      .finally(() => setReviewsLoading(false)); 
  };

  useEffect(() => {
    fetchReviews();
    // eslint-disable-next-line
  }, [id, axiosInstance, reviewPage]);

  useEffect(() => {
    if (user) {
      const checkPurchaseHistory = async () => {
        try {
          const ordersRes = await axiosInstance.get('/api/orders/?page_size=100');
          const deliveredOrders = (ordersRes.data.results || ordersRes.data).filter(o => o.status === 'delivered');
          for (let order of deliveredOrders) {
            const itemsRes = await axiosInstance.get(`/api/order-items/?order=${order.id}`);
            const foundItem = itemsRes.data.find(item => String(item.product) === String(id));
            if (foundItem) {
              setPurchaseDate(new Date(order.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }));
              break;
            }
          }
        } catch (err) { console.error("History check failed"); }
      };
      checkPurchaseHistory();
    }
  }, [id, user, axiosInstance]);

  const isAtLimit = product && quantity >= (product.stock || 0);

  const handleAddToCart = async () => {
    if (quantity > (product.stock || 0)) return toast.error(`Only ${product.stock} in stock!`);
    
    if (user) {
      try {
        await axiosInstance.post('/api/cart-items/', { product: id, quantity });
        toast.success(t => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span>🛒 <b>{product.name}</b> added to cart!</span>
            <Link to="/cart/" onClick={() => toast.dismiss(t.id)} style={{ color: '#0B8457', fontWeight: 'bold', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.9rem', marginTop: '4px' }}>Go to Cart <FaArrowRight size={12} /></Link>
          </div>
        ));
      } catch (err) {
        const msg = err.response?.data?.non_field_errors?.[0] || err.response?.data?.detail || '';
        if (msg.toLowerCase().includes('already')) toast.error(`⚠️ ${product.name} is already in your cart.`);
        else toast.error(`❌ Failed to add to cart.`);
      }
    } else {
      let tempCart = JSON.parse(localStorage.getItem('tempCart')) || [];
      const existing = tempCart.findIndex(item => String(item.product) === String(id));
      if (existing >= 0) {
        if (tempCart[existing].quantity + quantity > (product.stock || 0)) return toast.error(`Cannot exceed stock limit`);
        tempCart[existing].quantity += quantity;
      } else {
        tempCart.push({ id: `temp_${id}`, product: id, product_name: product.name, product_image: product.image_url, price: product.price, quantity: quantity, product_stock: product.stock || 0 });
      }
      localStorage.setItem('tempCart', JSON.stringify(tempCart));
      toast.success('🛒 Added to guest cart!');
    }
  };

  if (isLoading) {
    return (
      <AppLayout>
        <ContentGrid style={{ marginTop: '2rem' }}>
           <SkeletonRow style={{ height: '400px' }} />
           <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
             <SkeletonRow />
             <SkeletonRow />
             <SkeletonRow />
           </div>
        </ContentGrid>
      </AppLayout>
    );
  }

  if (!product) return null;

  const stockVal = product.stock || 0;

  return (
    <AppLayout>
      <GlowingPageContainer $maxWidth="1100px">
      {/* 🚀 TOP BUY SECTION: Clean Image Pane without overlapping badge */}
      <ContentGrid>
        <ImagePane 
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, type: 'spring', stiffness: 200, damping: 20 }}
        >
          <img src={product.image_url} alt={product.name} />
        </ImagePane>

        <InfoPane 
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, delay: 0.1, type: 'spring', stiffness: 200, damping: 20 }}
        >
          <AnimatePresence>
            {purchaseDate && (
              <PurchaseBanner initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
                <div className="icon-box"><FaCheckCircle size={18} /></div>
                <div>
                  <strong>Verified Purchase</strong>
                  <p>Delivered on {purchaseDate}</p>
                </div>
              </PurchaseBanner>
            )}
          </AnimatePresence>

          <TopMetaRow>
            <VendorTag>
              <FaStore /> Sold by: <strong>{product.vendor_name || 'EazyShop Official'}</strong>
            </VendorTag>

            {/* 🚀 POLISHED PLACEMENT: Cleanly docked alongside metadata */}
            <StockBadge $stock={stockVal}>
              {stockVal > 5 ? (
                <><FaCheckCircle size={12} /> In Stock</>
              ) : stockVal > 0 ? (
                <><FaExclamationTriangle size={12} /> Low Stock ({stockVal})</>
              ) : (
                <>Out of Stock</>
              )}
            </StockBadge>
          </TopMetaRow>

          <Title>{product.name}</Title>
          <Price>{formatINR(product.price)}</Price>

          <ActionCard>
            <div className="row">
              <span className="label">Quantity</span>
              <QuantityControl>
                <button onClick={() => setQuantity(prev => Math.max(1, prev - 1))} disabled={quantity <= 1}>-</button>
                <span>{quantity}</span>
                <button disabled={isAtLimit} onClick={() => setQuantity(prev => Math.min(stockVal, prev + 1))} style={{ opacity: isAtLimit ? 0.4 : 1, cursor: isAtLimit ? 'not-allowed' : 'pointer' }}>+</button>
              </QuantityControl>
            </div>
            
            <AddToCartButton 
              onClick={handleAddToCart} 
              disabled={stockVal === 0} 
              whileTap={{ scale: 0.98 }}
              $outOfStock={stockVal === 0}
            >
              <FaShoppingCart size={18} /> {stockVal === 0 ? 'Currently Unavailable' : 'Add to Cart'}
            </AddToCartButton>
          </ActionCard>
        </InfoPane>
      </ContentGrid>

      {/* 🚀 MIDDLE SECTION: Dedicated Description Canvas */}
      <DescriptionContainer
        as={motion.div}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <div className="header">
          <h2>Product Overview</h2>
          <div className="line"></div>
        </div>
        <DescriptionCard>
          {product.description}
        </DescriptionCard>
      </DescriptionContainer>

      {/* 🚀 BOTTOM SECTION: Reviews */}
      <ReviewsSection
        as={motion.div}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <div className="header">
          <h2>Customer Reviews</h2>
          <div className="line"></div>
        </div>
        
        {reviewsLoading ? (
           <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem', maxWidth: '800px', margin: '0 auto' }}>
             {[...Array(2)].map((_, index) => <SkeletonRow key={index} />)}
           </div>
        ) : reviews.length === 0 ? (
          <EmptyReviews>
            <span className="emoji">📝</span>
            <p>No reviews yet. Be the first to share your thoughts!</p>
          </EmptyReviews>
        ) : (
          <ReviewGrid>
            {reviews.map(review => (
              <ReviewCard key={review.id}>
                <div className="reviewer">
                  <div className="avatar">{review.username.charAt(0).toUpperCase()}</div>
                  <div className="details">
                    <strong>{review.username}</strong>
                    <StarsContainer>
                      {Array.from({ length: 5 }, (_, i) => <FaStar key={i} size={14} color={i < review.rating ? '#F59E0B' : '#E2E8F0'} />)}
                    </StarsContainer>
                  </div>
                </div>
                <p className="comment">"{review.comment}"</p>
              </ReviewCard>
            ))}
          </ReviewGrid>
        )}

        {!reviewsLoading && totalReviewPages > 1 && (
          <PaginationWrapper>
            <PageButton onClick={() => setReviewPage(p => Math.max(p - 1, 1))} disabled={reviewPage === 1}>&larr; Prev</PageButton>
            <PageInfo>Page {reviewPage} of {totalReviewPages}</PageInfo>
            <PageButton onClick={() => setReviewPage(p => Math.min(p + 1, totalReviewPages))} disabled={reviewPage === totalReviewPages}>Next &rarr;</PageButton>
          </PaginationWrapper>
        )}
        </ReviewsSection>
      </GlowingPageContainer>
    </AppLayout>
  );
};

export default ProductDetail;

// ==========================================
// COMPONENT STYLES
// ==========================================

const ContentGrid = styled.div`
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 1fr;
  gap: 3rem;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1.5rem;

  @media (min-width: 900px) {
    grid-template-columns: 1fr 1fr;
    align-items: start; 
  }
`;

const ImagePane = styled(motion.div)`
  background: #ffffff;
  border-radius: 24px;
  padding: 3rem;
  border: 1px solid rgba(11, 132, 87, 0.12);
  box-shadow: 0 10px 40px -10px rgba(0,0,0,0.05);
  display: flex;
  align-items: center;
  justify-content: center;
  
  img {
    width: 100%;
    max-width: 450px;
    object-fit: contain;
    mix-blend-mode: multiply;
  }
`;

const TopMetaRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  gap: 0.5rem;
`;

const StockBadge = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.35rem 0.9rem;
  border-radius: 50px;
  background: ${props => props.$stock > 5 ? 'rgba(236, 253, 245, 0.9)' : props.$stock > 0 ? 'rgba(254, 243, 199, 0.9)' : 'rgba(254, 226, 226, 0.9)'};
  color: ${props => props.$stock > 5 ? '#047857' : props.$stock > 0 ? '#B45309' : '#B91C1C'};
  border: 1px solid ${props => props.$stock > 5 ? 'rgba(16, 185, 129, 0.3)' : props.$stock > 0 ? 'rgba(245, 158, 11, 0.3)' : 'rgba(239, 68, 68, 0.3)'};
`;

const InfoPane = styled(motion.div)`
  display: flex;
  flex-direction: column;
`;

const PurchaseBanner = styled(motion.div)`
  display: flex;
  align-items: center;
  gap: 1rem;
  background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
  border: 1px solid #A7F3D0;
  padding: 1rem 1.5rem;
  border-radius: 16px;
  margin-bottom: 2rem;
  
  .icon-box {
    color: #059669;
    display: flex;
  }
  
  strong { color: #065F46; font-size: 0.95rem; }
  p { color: #047857; margin: 0.2rem 0 0 0; font-size: 0.85rem; font-weight: 500; }
`;

const VendorTag = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: #64748B;
  font-size: 0.95rem;
  margin-bottom: 0;
  
  svg { color: #0B8457; }
  strong { color: #0F172A; }
`;

const Title = styled.h1`
  font-size: clamp(2.2rem, 4vw, 3rem);
  font-weight: 900;
  color: #0F172A;
  margin: 0 0 1rem 0;
  letter-spacing: -1px;
  line-height: 1.2;
`;

const Price = styled.div`
  font-size: 2.5rem;
  font-weight: 800;
  color: #0B8457;
  margin-bottom: 2rem;
  letter-spacing: -1px;
`;

const ActionCard = styled.div`
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 20px;
  padding: 1.5rem;
  box-shadow: 0 10px 30px -5px rgba(0,0,0,0.05);

  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
  }
  
  .label {
    font-weight: 700;
    color: #334155;
    font-size: 1.05rem;
  }
`;

const QuantityControl = styled.div`
  display: flex; 
  align-items: center; 
  background: #F8FAFC; 
  border-radius: 50px; 
  padding: 0.35rem;
  border: 1px solid #E2E8F0;
  
  button { 
    background: #ffffff; 
    color: #334155; 
    border: none; 
    width: 34px; 
    height: 34px; 
    border-radius: 50%; 
    cursor: pointer; 
    font-weight: 800; 
    font-size: 1.1rem;
    display: flex; 
    align-items: center; 
    justify-content: center; 
    box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
    transition: all 0.2s ease;
    
    &:hover:not(:disabled) { background: #0B8457; color: white; }
  }
  
  span { min-width: 40px; text-align: center; font-size: 1.1rem; font-weight: 700; color: #0F172A; }
`;

const AddToCartButton = styled(motion.button)`
  width: 100%; 
  padding: 1rem; 
  background: ${props => props.$outOfStock ? '#F1F5F9' : 'linear-gradient(135deg, #0B8457 0%, #075E3E 100%)'}; 
  color: ${props => props.$outOfStock ? '#94A3B8' : '#ffffff'}; 
  border: none; 
  border-radius: 14px; 
  font-weight: 700; 
  font-size: 1.1rem; 
  cursor: ${props => props.$outOfStock ? 'not-allowed' : 'pointer'}; 
  display: flex; 
  align-items: center; 
  justify-content: center; 
  gap: 0.8rem; 
  position: relative;
  overflow: hidden;
  box-shadow: ${props => props.$outOfStock ? 'none' : '0 6px 20px rgba(11, 132, 87, 0.25)'};
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
  
  &:hover:not(:disabled) { box-shadow: 0 8px 25px rgba(11, 132, 87, 0.4); }
`;

const DescriptionContainer = styled.div`
  max-width: 1200px;
  margin: 4rem auto 0 auto;
  padding: 0 1.5rem;

  .header {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    margin-bottom: 2rem;
    
    h2 {
      font-size: 1.6rem;
      font-weight: 800;
      color: #0F172A;
      margin: 0;
      white-space: nowrap;
    }
    
    .line {
      height: 1px;
      flex-grow: 1;
      background: #E2E8F0;
    }
  }
`;

const DescriptionCard = styled.div`
  background: #ffffff;
  border-radius: 24px;
  padding: 2.5rem;
  border: 1px solid rgba(11, 132, 87, 0.08);
  box-shadow: 0 10px 40px -10px rgba(0,0,0,0.03);
  font-size: 1.1rem;
  color: #475569;
  line-height: 1.8;
  white-space: pre-line;
`;

const ReviewsSection = styled.div`
  max-width: 1200px;
  margin: 4rem auto 0 auto;
  padding: 0 1.5rem;
  
  .header {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    margin-bottom: 2rem;
    
    h2 {
      font-size: 1.6rem;
      font-weight: 800;
      color: #0F172A;
      margin: 0;
      white-space: nowrap;
    }
    
    .line {
      height: 1px;
      flex-grow: 1;
      background: #E2E8F0;
    }
  }
`;

const EmptyReviews = styled.div`
  text-align: center;
  padding: 3rem;
  background: #ffffff;
  border-radius: 24px;
  border: 1px dashed #CBD5E1;
  max-width: 600px;
  margin: 0 auto;
  
  .emoji { font-size: 2.5rem; display: block; margin-bottom: 1rem; }
  p { color: #64748B; font-size: 1.05rem; }
`;

const ReviewGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr;
  gap: 1.5rem;
  
  @media (min-width: 768px) {
    grid-template-columns: 1fr 1fr;
  }
`;

const ReviewCard = styled.div`
  background: #ffffff;
  border-radius: 20px;
  padding: 1.5rem;
  border: 1px solid rgba(11, 132, 87, 0.08);
  box-shadow: 0 4px 20px rgba(0,0,0,0.02);
  
  .reviewer {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }
  
  .avatar {
    width: 45px;
    height: 45px;
    border-radius: 50%;
    background: #ECFDF5;
    color: #0B8457;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 1.2rem;
  }
  
  .details strong {
    display: block;
    color: #0F172A;
    font-size: 1.05rem;
  }
  
  .comment {
    color: #475569;
    font-style: italic;
    line-height: 1.6;
    margin: 0;
  }
`;

const StarsContainer = styled.div`
  display: flex;
  gap: 0.2rem;
  margin-top: 0.3rem;
`;

const PaginationWrapper = styled.div`
  display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 3rem;
`;

const PageButton = styled.button`
  padding: 0.6rem 1.4rem; 
  border-radius: 50px; 
  border: none; 
  font-weight: 700; 
  background: ${props => props.disabled ? '#F1F5F9' : '#0B8457'}; 
  color: ${props => props.disabled ? '#94A3B8' : 'white'}; 
  cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'}; 
  transition: all 0.2s ease; 
  
  &:hover:not(:disabled) { 
    background: #086341; 
    transform: translateY(-1px); 
  }
`;

const PageInfo = styled.span`
  font-weight: 700; color: #334155; font-size: 0.95rem;
`;