// src/pages/Cart.jsx
import { useContext, useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import AuthContext from '../context/AuthContext';
import styled from 'styled-components';
import { toast } from "react-hot-toast";
import { SkeletonRow } from '../components/SkeletonLoader';
import { FaTrashAlt, FaHeart, FaRegHeart, FaArrowRight, FaShieldAlt, FaExclamationTriangle } from 'react-icons/fa';
import { PageHeader, GlowingPageContainer } from '../styles/SharedPageStyles';
import AppLayout from '../components/AppLayout';
import ModalPortal from '../components/ModalPortal';
import { formatINR } from '../utils/currency';

const ConfirmationModal = ({ isOpen, onClose, onConfirm }) => {
  return (
    <AnimatePresence>
      {isOpen && (
        <ModalPortal>
          <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ModalCard initial={{ scale: 0.95, opacity: 0, y: 20 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.95, opacity: 0, y: 20 }}>
              <ModalIconWrapper><FaExclamationTriangle size={24} /></ModalIconWrapper>
              <h3>Remove from Cart?</h3>
              <p>Are you sure you want to remove this item from your shopping cart?</p>
              <ButtonGroup>
                <CancelButton onClick={onClose} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>Cancel</CancelButton>
                <ConfirmButton onClick={onConfirm} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>Yes, Remove</ConfirmButton>
              </ButtonGroup>
            </ModalCard>
          </Overlay>
        </ModalPortal>
      )}
    </AnimatePresence>
  );
};

const CartQuantityController = ({ itemId, initialQuantity, stockLimit, onQuantityUpdate }) => {
  const [localQuantity, setLocalQuantity] = useState(initialQuantity);
  const isAtLimit = localQuantity >= stockLimit;

  useEffect(() => { setLocalQuantity(initialQuantity); }, [initialQuantity]);

  useEffect(() => {
    if (localQuantity === initialQuantity) return;
    const delayDebounceFn = setTimeout(() => {
      if (localQuantity > 0 && localQuantity <= stockLimit) onQuantityUpdate(itemId, localQuantity);
    }, 500);
    return () => clearTimeout(delayDebounceFn);
  }, [localQuantity, itemId, initialQuantity, onQuantityUpdate, stockLimit]);

  const handleIncrement = () => { if (!isAtLimit) setLocalQuantity(prev => Number(prev) + 1); };
  const handleDecrement = () => setLocalQuantity(prev => (prev > 1 ? prev - 1 : 1));
  const handleManualInput = (e) => {
    const val = e.target.value;
    if (val === '') { setLocalQuantity(''); return; }
    const parsed = parseInt(val, 10);
    if (!isNaN(parsed) && parsed > 0) setLocalQuantity(Math.min(parsed, stockLimit));
  };
  const handleBlur = () => { if (localQuantity === '' || localQuantity < 1) setLocalQuantity(initialQuantity); };

  return (
    <QuantityControl>
      <button onClick={handleDecrement} disabled={localQuantity <= 1}>-</button>
      <input type="number" min="1" value={localQuantity} onChange={handleManualInput} onBlur={handleBlur} />
      <button disabled={isAtLimit} onClick={handleIncrement} style={{ opacity: isAtLimit ? 0.4 : 1, cursor: isAtLimit ? 'not-allowed' : 'pointer' }}>+</button>
    </QuantityControl>
  );
};

const Cart = () => {
  const { axiosInstance, user } = useContext(AuthContext);
  const navigate = useNavigate();
  const [cartItems, setCartItems] = useState([]);
  const [wishlistIds, setWishlistIds] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [itemToRemove, setItemToRemove] = useState(null);

  const fetchCartItems = async () => {
    setIsLoading(true);
    if (user) {
      try {
        const res = await axiosInstance.get('/api/cart-items/');
        setCartItems(res.data);
      } catch (err) { console.error(err); }
    } else {
      const tempCart = JSON.parse(localStorage.getItem('tempCart')) || [];
      setCartItems(tempCart);
    }
    setIsLoading(false); 
  };

  const fetchWishlist = async () => {
    if (!user) return;
    try {
      const res = await axiosInstance.get('/api/wishlist/');
      setWishlistIds(res.data.map(item => item.product.id));
    } catch (err) { console.error(err); }
  };

  const handleAddToWishlist = async (productId) => {
    if (!user) {
      toast.error('Please log in to use your wishlist!');
      navigate('/login');
      return; 
    }
    if (wishlistIds.includes(productId)) return;
    try {
      await axiosInstance.post('/api/wishlist/', { product_id: productId });
      setWishlistIds(prev => [...prev, productId]);
      toast.success('Added to wishlist!');
    } catch (err) { console.error(err); }
  };

  const handleQuantityChange = async (id, quantity) => {
    if (user) {
      try {
        setCartItems(prevItems => prevItems.map(item => item.id === id ? { ...item, quantity } : item));
        await axiosInstance.patch(`/api/cart-items/${id}/`, { quantity });
      } catch (err) { fetchCartItems(); }
    } else {
      let tempCart = JSON.parse(localStorage.getItem('tempCart')) || [];
      tempCart = tempCart.map(item => item.id === id ? { ...item, quantity } : item);
      localStorage.setItem('tempCart', JSON.stringify(tempCart));
      setCartItems(tempCart);
    }
  };

  const promptRemoveItem = (id) => {
    setItemToRemove(id);
    setIsModalOpen(true);
  };

  const executeRemoveItem = async () => {
    if (user) {
      try {
        await axiosInstance.delete(`/api/cart-items/${itemToRemove}/`);
        setCartItems(prev => prev.filter(item => item.id !== itemToRemove));
      } catch (err) { console.error(err); } 
      finally { setIsModalOpen(false); setItemToRemove(null); }
    } else {
      let tempCart = JSON.parse(localStorage.getItem('tempCart')) || [];
      tempCart = tempCart.filter(item => item.id !== itemToRemove);
      localStorage.setItem('tempCart', JSON.stringify(tempCart));
      setCartItems(tempCart);
      setIsModalOpen(false);
      setItemToRemove(null);
    }
  };

  const handleProceedToCheckout = () => {
    if (cartItems.length === 0) return;
    if (!user) {
      toast('🔒 Please log in to secure your checkout!', { style: { background: '#0F172A', color: '#fff' }});
      navigate('/login', { state: { from: '/checkout/' } });
    } else {
      navigate('/checkout/');
    }
  };

  useEffect(() => {
    fetchCartItems();
    fetchWishlist();
    // eslint-disable-next-line
  }, [axiosInstance, user]);

  const cartTotal = cartItems.reduce((sum, item) => sum + item.quantity * Number(item.price), 0);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 300, damping: 24 } }
  };

  return (
    <AppLayout>
      <GlowingPageContainer $maxWidth="1100px">
        <AmbientBackground />
        <ConfirmationModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} onConfirm={executeRemoveItem} />

        <CartContainer>
          <PageHeader initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: "easeOut" }}>
            <h1>Your Shopping Cart</h1>
            <p>Review your items before proceeding to secure checkout.</p>
          </PageHeader>

          {isLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%', marginTop: '2rem' }}>
              {[...Array(3)].map((_, index) => <SkeletonRow key={index} style={{ height: '120px', borderRadius: '20px' }} />)}
            </div>
          ) : cartItems.length === 0 ? (
            <EmptyState initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
              <span className="emoji">🛒</span>
              <h3>Your cart is empty</h3>
              <p>Looks like you haven't added anything to your cart yet.</p>
              <Link to="/products" className="shopping-btn">Start Shopping <FaArrowRight size={12} /></Link>
            </EmptyState>
          ) : (
            <ContentGrid>
              <CartList as={motion.div} variants={containerVariants} initial="hidden" animate="visible">
                <AnimatePresence mode='popLayout'>
                  {cartItems.map(item => (
                    <CartItemCard key={item.id} layout variants={itemVariants} initial="hidden" animate="visible" exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}>
                      <ImageWrapper>
                        <img src={item.product_image} alt={item.product_name} />
                      </ImageWrapper>
                      
                      <ProductDetails>
                        <div className="title-row">
                          <Link to={`/products/${item.product}`} className="title">{item.product_name}</Link>
                          <TotalPrice>{formatINR((item.quantity * Number(item.price)))}</TotalPrice>
                        </div>
                        
                        <div className="price-row">
                          <UnitPrice>{formatINR(item.price)} each</UnitPrice>
                        </div>

                        <ControlsRow>
                          <CartQuantityController itemId={item.id} initialQuantity={item.quantity} stockLimit={item.product_stock || 99} onQuantityUpdate={handleQuantityChange} />
                          
                          <ActionsGroup>
                            <WishlistButton onClick={() => handleAddToWishlist(item.product)} disabled={wishlistIds.includes(item.product)} title="Add to Wishlist">
                              {wishlistIds.includes(item.product) ? <FaHeart color="#DC2626" /> : <FaRegHeart />}
                            </WishlistButton>
                            <div className="divider"></div>
                            <RemoveButton onClick={() => promptRemoveItem(item.id)}>
                              <FaTrashAlt /> Remove
                            </RemoveButton>
                          </ActionsGroup>
                        </ControlsRow>
                      </ProductDetails>
                    </CartItemCard>
                  ))}
                </AnimatePresence>
              </CartList>

              <SummarySticky>
                <CheckoutSummary initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
                  <h3>Order Summary</h3>
                  <div className="summary-row">
                    <span>Subtotal</span>
                    <span>{formatINR(cartTotal)}</span>
                  </div>
                  <div className="summary-row">
                    <span>Shipping</span>
                    <span className="free">Calculated at checkout</span>
                  </div>
                  <div className="summary-divider"></div>
                  <div className="summary-total">
                    <span>Total</span>
                    <span>{formatINR(cartTotal)}</span>
                  </div>

                  <CheckoutButton onClick={handleProceedToCheckout} whileTap={{ scale: 0.98 }}>
                    Proceed to Checkout <FaArrowRight />
                  </CheckoutButton>
                  
                  <SecureBadge>
                    <FaShieldAlt /> SSL Secure Encrypted Checkout
                  </SecureBadge>
                </CheckoutSummary>
              </SummarySticky>
            </ContentGrid>
          )}
        </CartContainer>
      </GlowingPageContainer>
    </AppLayout>
  );
};

export default Cart;

const AmbientBackground = styled.div`
  position: absolute; top: 0; left: 50%; transform: translateX(-50%); width: 100%; max-width: 1400px; height: 600px;
  background: radial-gradient(circle at 50% 10%, rgba(11, 132, 87, 0.08) 0%, transparent 60%); pointer-events: none; z-index: 0;
`;

const CartContainer = styled.div`
  position: relative; z-index: 1; max-width: 1200px; margin: 0 auto; padding: 0 1.5rem;
  @media (max-width: 768px) { padding: 0 0.75rem; }
`;

const ContentGrid = styled.div`
  display: grid; grid-template-columns: 1fr; gap: 2.5rem; align-items: start;
  @media (min-width: 900px) { grid-template-columns: 1.8fr 1fr; }
`;

const CartList = styled(motion.div)`
  display: flex; flex-direction: column; gap: 1.5rem;
`;

const CartItemCard = styled(motion.div)`
  background: #ffffff; padding: 1.5rem; border-radius: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.03);
  border: 1px solid rgba(11, 132, 87, 0.08); display: flex; flex-direction: column; gap: 1.5rem;
  @media (min-width: 600px) { flex-direction: row; align-items: center; }
  @media (max-width: 768px) { padding: 1rem; }
`;

const ImageWrapper = styled.div`
  width: 120px; height: 120px; min-width: 120px; background: #F8FAFC; border-radius: 16px;
  display: flex; align-items: center; justify-content: center; padding: 1rem; border: 1px solid #F1F5F9; box-sizing: border-box;
  img { width: 100%; height: 100%; object-fit: contain; mix-blend-mode: multiply; }
  @media (max-width: 600px) { width: 100%; height: 160px; }
`;

const ProductDetails = styled.div`
  flex-grow: 1; display: flex; flex-direction: column; width: 100%;
  .title-row {
    display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 0.4rem;
    .title { font-size: 1.15rem; font-weight: 800; color: #0F172A; text-decoration: none; line-height: 1.4; transition: color 0.2s; &:hover { color: #0B8457; } }
  }
  .price-row { margin-bottom: 1.2rem; }
`;

const UnitPrice = styled.span` color: #64748B; font-size: 0.95rem; font-weight: 500; `;
const TotalPrice = styled.strong` font-size: 1.25rem; font-weight: 900; color: #0F172A; white-space: nowrap; `;

const ControlsRow = styled.div`
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;
  margin-top: auto; padding-top: 1rem; border-top: 1px solid #F1F5F9;
`;

const QuantityControl = styled.div`
  display: flex; align-items: center; background: #F8FAFC; border-radius: 50px; padding: 0.25rem; border: 1px solid #E2E8F0;
  button {
    background: #ffffff; color: #334155; border: none; width: 32px; height: 32px; border-radius: 50%; cursor: pointer;
    font-weight: 800; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); transition: all 0.2s;
    &:hover:not(:disabled) { background: #0B8457; color: white; }
  }
  input {
    width: 40px; text-align: center; font-size: 1rem; font-weight: 700; color: #0F172A; background: transparent; border: none; outline: none;
  }
`;

const ActionsGroup = styled.div`
  display: flex; align-items: center; gap: 1rem;
  .divider { width: 1px; height: 20px; background: #E2E8F0; }
`;

const WishlistButton = styled.button`
  background: none; border: none; color: #94A3B8; cursor: ${props => props.disabled ? 'default' : 'pointer'};
  font-size: 1.3rem; display: flex; align-items: center; transition: all 0.2s;
  &:hover:not(:disabled) { color: #DC2626; transform: scale(1.1); }
`;

const RemoveButton = styled.button`
  background: transparent; color: #EF4444; border: none; font-size: 0.95rem; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; gap: 0.4rem; padding: 0.5rem 0.8rem; border-radius: 8px; transition: all 0.2s;
  &:hover { background: #FEF2F2; color: #DC2626; }
`;

const SummarySticky = styled.div`
  position: sticky; top: 100px;
  @media (max-width: 900px) { position: static; }
`;

const CheckoutSummary = styled(motion.div)`
  background: rgba(255, 255, 255, 0.8); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  border-radius: 24px; padding: 2rem; border: 1px solid rgba(11, 132, 87, 0.12); box-shadow: 0 10px 40px -10px rgba(0,0,0,0.06);
  h3 { font-size: 1.4rem; font-weight: 800; color: #0F172A; margin: 0 0 1.5rem 0; }
  .summary-row {
    display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1.2rem;
    color: #475569; font-size: 1.05rem; font-weight: 500;
    span:last-child { text-align: right; flex-shrink: 1; }
    .free { color: #0B8457; font-size: 0.9rem; font-style: italic; }
  }
  .summary-divider { height: 1px; background: #E2E8F0; margin: 1.5rem 0; }
  .summary-total {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem;
    span:first-child { font-size: 1.2rem; font-weight: 700; color: #0F172A; }
    span:last-child { font-size: 1.8rem; font-weight: 900; color: #0B8457; letter-spacing: -1px; }
  }
  @media (max-width: 768px) { padding: 1.25rem; }
`;

const CheckoutButton = styled(motion.button)`
  width: 100%; padding: 1.1rem; background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%);
  color: #ffffff; border: none; border-radius: 14px; font-weight: 800; font-size: 1.15rem; cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 0.8rem; box-shadow: 0 6px 20px rgba(11, 132, 87, 0.25);
  transition: all 0.3s ease;
  &:hover { box-shadow: 0 8px 25px rgba(11, 132, 87, 0.4); }
`;

const SecureBadge = styled.div`
  display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-top: 1.5rem;
  color: #64748B; font-size: 0.85rem; font-weight: 600;
  svg { color: #10B981; }
`;

const EmptyState = styled(motion.div)`
  text-align: center; padding: 6rem 2rem; background: #ffffff; border-radius: 24px; border: 1px dashed #CBD5E1; max-width: 600px; margin: 0 auto;
  .emoji { font-size: 4rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.8rem; font-weight: 900; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1.1rem; margin-bottom: 2rem; }
  .shopping-btn {
    display: inline-flex; align-items: center; gap: 0.5rem; background: #0B8457; color: white; text-decoration: none;
    padding: 0.9rem 2rem; border-radius: 50px; font-weight: 700; font-size: 1.05rem; transition: all 0.2s ease;
    box-shadow: 0 4px 14px rgba(11, 132, 87, 0.2);
    &:hover { background: #086341; transform: translateY(-2px); box-shadow: 0 6px 20px rgba(11, 132, 87, 0.3); }
  }
`;

const Overlay = styled(motion.div)`
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 1.5rem;
`;

const ModalCard = styled(motion.div)`
  background: #ffffff; padding: 2.5rem 2rem; border-radius: 24px; width: 100%; max-width: 420px; text-align: center;
  box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);
  h3 { margin: 1rem 0 0.5rem 0; color: #0F172A; font-size: 1.6rem; font-weight: 800; }
  p { color: #64748B; margin-bottom: 2rem; line-height: 1.6; font-size: 1.05rem; }
`;

const ModalIconWrapper = styled.div`
  width: 64px; height: 64px; background: #FEF2F2; color: #EF4444; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; margin: 0 auto;
`;

const ButtonGroup = styled.div` display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; `;

const CancelButton = styled(motion.button)`
  padding: 0.9rem; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 1.05rem; background: #ffffff; color: #475569;
  &:hover { background: #F8FAFC; color: #0F172A; }
`;

const ConfirmButton = styled(motion.button)`
  padding: 0.9rem; border: none; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 1.05rem; background: #EF4444; color: #ffffff;
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
  &:hover { background: #DC2626; box-shadow: 0 6px 16px rgba(239, 68, 68, 0.3); }
`;