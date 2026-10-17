// src/pages/Wishlist.jsx
import { useEffect, useState, useContext } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import AuthContext from '../context/AuthContext';
import { FaTrashAlt, FaShoppingCart, FaArrowRight, FaHeart, FaExclamationTriangle } from 'react-icons/fa';
import { toast } from "react-hot-toast";
import { Link } from 'react-router-dom';
import { SkeletonProductCard } from '../components/SkeletonLoader';
import {PageHeader,GlowingPageContainer} from '../styles/SharedPageStyles';
import AppLayout from '../components/AppLayout';
import ModalPortal from '../components/ModalPortal';
import { formatINR } from '../utils/currency';

const Wishlist = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [wishlist, setWishlist] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  
  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [itemToRemove, setItemToRemove] = useState(null);

  useEffect(() => {
    fetchWishlist();
    // eslint-disable-next-line
  }, []);

  const fetchWishlist = async () => {
    setIsLoading(true);
    try {
      const res = await axiosInstance.get('/api/wishlist/');
      const rawData = res.data.results || res.data || [];
      
      const formatted = await Promise.all(
        rawData.map(async (item) => {
          let prod = item.product;

          if (typeof prod !== 'object' || prod === null || !prod.name) {
            const prodId = typeof prod === 'object' && prod !== null ? (prod.id || prod.pk) : prod;
            if (prodId) {
              try {
                const prodRes = await axiosInstance.get(`/api/products/${prodId}/`);
                prod = prodRes.data;
              } catch (err) {
                prod = { id: prodId, name: 'Product Item', price: 0, image_url: '' };
              }
            }
          }

          return {
            id: item.id || item.pk,
            product: {
              id: prod?.id || prod?.pk || item.product_id || Math.random(),
              name: prod?.name || prod?.product_name || item.name || 'Product Item',
              price: Number(prod?.price || item.price || 0),
              image_url: prod?.image_url || prod?.image || item.image_url || ''
            }
          };
        })
      );

      setWishlist(formatted);
    } catch (err) {
      console.error("Wishlist load error:", err);
      toast.error('❌ Failed to load wishlist');
      setWishlist([]);
    } finally {
      setIsLoading(false);
    }
  };

  const promptRemove = (id) => {
    setItemToRemove(id);
    setIsModalOpen(true);
  };

  const executeRemove = async () => {
    if (!itemToRemove) return;
    try {
      await axiosInstance.delete(`/api/wishlist/${itemToRemove}/`);
      toast.success('💔 Removed from wishlist');
      fetchWishlist();
    } catch (err) {
      toast.error('❌ Failed to remove item');
    } finally {
      setIsModalOpen(false);
      setItemToRemove(null);
    }
  };

  const addToCart = async (product) => {
    try {
      await axiosInstance.post('/api/cart-items/', {
        product: product.id,
        quantity: 1,
      });
      toast.success(
        (t) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span>🛒 <b>{product.name}</b> added to cart!</span>
            <Link to="/cart/" onClick={() => toast.dismiss(t.id)} style={{ color: '#0B8457', fontWeight: 'bold', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.9rem', marginTop: '4px' }}>
              Go to Cart <FaArrowRight size={12} />
            </Link>
          </div>
        )
      );
    } catch (err) {
      const serverMessage = err.response?.data?.non_field_errors?.[0] || err.response?.data?.error || err.response?.data?.detail;
      
      if (serverMessage && serverMessage.toLowerCase().includes('already')) {
        toast(
          (t) => (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <span>⚠️ <b>{product.name}</b> is already in your cart.</span>
              <Link to="/cart/" onClick={() => toast.dismiss(t.id)} style={{ color: '#DC2626', fontWeight: 'bold', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '5px', fontSize: '0.9rem', marginTop: '4px' }}>
                Go to Cart <FaArrowRight size={12} />
              </Link>
            </div>
          )
        );
      } else {
        toast.error(`❌ Failed to add ${product.name} to cart.`);
      }
    }
  };

  // 🚀 Staggered Animation Variants
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.08,
        delayChildren: 0.05
      }
    }
  };

  const cardVariants = {
    hidden: { opacity: 0, y: 25 },
    visible: { 
      opacity: 1, 
      y: 0, 
      transition: { type: 'spring', stiffness: 260, damping: 20 } 
    }
  };

  return (
    <AppLayout>   
      <GlowingPageContainer $maxWidth="1100px">
      {/* --- Confirmation Modal --- */}
      <AnimatePresence>
        {isModalOpen && (
          <ModalPortal>
          <Overlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <ModalCard initial={{ scale: 0.95, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.95, opacity: 0, y: 10 }}>
              <ModalIconWrapper>
                <FaExclamationTriangle size={22} />
              </ModalIconWrapper>
              <h3>Remove from Wishlist?</h3>
              <p>Are you sure you want to remove this item from your saved favorites?</p>
              <ButtonGroup>
                <ModalSecondaryButton onClick={() => setIsModalOpen(false)}>Cancel</ModalSecondaryButton>
                <ModalDangerButton onClick={executeRemove}>Yes, Remove</ModalDangerButton>
              </ButtonGroup>
            </ModalCard>
          </Overlay>
          </ModalPortal>
        )}
      </AnimatePresence>

      <PageHeader
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
        <BadgeTag><FaHeart size={12} /> Saved Favorites</BadgeTag>
        <h1>My Wishlist</h1>
        <p>Your curated list of premium items saved for later consideration.</p>
      </PageHeader>

      <WishlistContainer>
        {isLoading ? (
          <WishlistGrid>
            {[...Array(4)].map((_, index) => <SkeletonProductCard key={index} />)}
          </WishlistGrid>
        ) : wishlist.length === 0 ? (
          <EmptyState
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <span className="emoji">💖</span>
            <h3>Your Wishlist is Empty</h3>
            <p>You haven't saved any products to your wishlist yet. Explore our collection and save your favorites!</p>
            <Link to="/products/" className="explore-btn">
              Explore Catalog <FaArrowRight size={12} />
            </Link>
          </EmptyState>
        ) : (
          <WishlistGrid
            key={wishlist.length} // 🚀 Forces stagger sequence to fire fresh on data load
            as={motion.div}
            variants={containerVariants}
            initial="hidden"
            animate="visible"
          >
            <AnimatePresence mode='popLayout'>
              {wishlist.map((item) => (
                <WishlistCard
                  key={item.id}
                  variants={cardVariants}
                  whileHover={{ y: -6 }}
                >
                  <ImageWrapper>
                    <Link to={`/products/${item.product.id}/`}>
                      <img
                        src={item.product.image_url}
                        alt={item.product.name}
                      />
                    </Link>
                  </ImageWrapper>
                  
                  <Info>
                    <Link to={`/products/${item.product.id}/`} className="title">
                      {item.product.name}
                    </Link>
                    <Price>{formatINR(item.product.price)}</Price>
                  </Info>

                  <Actions>
                    <AddToCartBtn 
                      onClick={() => addToCart(item.product)}
                      whileTap={{ scale: 0.96 }}
                    >
                      <FaShoppingCart /> Add to Cart
                    </AddToCartBtn>
                    <RemoveBtn 
                      onClick={() => promptRemove(item.id)}
                      whileTap={{ scale: 0.96 }}
                    >
                      <FaTrashAlt />
                    </RemoveBtn>
                  </Actions>
                </WishlistCard>
              ))}
            </AnimatePresence>
          </WishlistGrid>
        )}
        </WishlistContainer>
      </GlowingPageContainer>
      </AppLayout> 
  );
};

export default Wishlist;

// ==========================================
// SAAS LEVEL STYLED COMPONENTS
// ==========================================


const BadgeTag = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
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

const WishlistContainer = styled.div`
  position: relative;
  z-index: 1;
  max-width: 1250px;
  margin: 0 auto;
  padding: 0 1.5rem;
  box-sizing: border-box;
`;

const WishlistGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
  gap: 2rem;
`;

const WishlistCard = styled(motion.div)`
  background: #ffffff;
  border-radius: 24px;
  padding: 1.5rem;
  border: 1px solid rgba(11, 132, 87, 0.12);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  transition: border-color 0.3s ease, box-shadow 0.3s ease;

  &:hover {
    border-color: rgba(11, 132, 87, 0.4);
    box-shadow: 0 20px 40px -10px rgba(11, 132, 87, 0.15);
  }
`;

const ImageWrapper = styled.div`
  width: 100%;
  aspect-ratio: 1 / 1;
  background: #F8FAFC;
  border-radius: 18px;
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
    transform: scale(1.08);
  }
`;

const Info = styled.div`
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  margin-bottom: 1.2rem;

  .title {
    font-size: 1.15rem;
    font-weight: 800;
    color: #0F172A;
    text-decoration: none;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    margin-bottom: 0.5rem;
    transition: color 0.2s;

    &:hover {
      color: #0B8457;
    }
  }
`;

const Price = styled.div`
  font-size: 1.4rem;
  font-weight: 900;
  color: #0B8457;
  letter-spacing: -0.5px;
  margin-top: auto;
`;

const Actions = styled.div`
  display: flex;
  gap: 0.6rem;
  width: 100%;
`;

const AddToCartBtn = styled(motion.button)`
  flex: 1;
  padding: 0.85rem;
  background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%);
  color: #ffffff;
  border: none;
  border-radius: 14px;
  font-weight: 700;
  font-size: 0.9rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  position: relative;
  overflow: hidden;
  box-shadow: 0 4px 14px rgba(11, 132, 87, 0.25);
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
    animation: shimmer 4s infinite;
  }

  @keyframes shimmer {
    0% { left: -150%; }
    20% { left: 200%; }
    100% { left: 200%; }
  }

  &:hover {
    box-shadow: 0 6px 20px rgba(11, 132, 87, 0.4);
  }
`;

const RemoveBtn = styled(motion.button)`
  padding: 0.85rem 1rem;
  background: #FEF2F2;
  color: #DC2626;
  border: 1px solid #FCA5A5;
  border-radius: 14px;
  cursor: pointer;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;

  &:hover {
    background: #FEE2E2;
  }
`;

const EmptyState = styled(motion.div)`
  text-align: center;
  padding: 5rem 2rem;
  background: #ffffff;
  border-radius: 24px;
  border: 1px dashed #CBD5E1;
  max-width: 600px;
  margin: 0 auto;
  box-shadow: 0 10px 30px rgba(0,0,0,0.02);

  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; margin-bottom: 1.5rem; line-height: 1.5; }

  .explore-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: linear-gradient(135deg, #0B8457 0%, #075E3E 100%);
    color: white;
    text-decoration: none;
    padding: 0.85rem 2rem;
    border-radius: 50px;
    font-weight: 700;
    box-shadow: 0 4px 14px rgba(11, 132, 87, 0.25);
    transition: all 0.2s ease;

    &:hover {
      box-shadow: 0 6px 20px rgba(11, 132, 87, 0.4);
      transform: translateY(-1px);
    }
  }
`;

// --- Modal Styled Components ---
const Overlay = styled(motion.div)`
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  z-index: 10000; padding: 1rem;
`;

const ModalCard = styled(motion.div)`
  position: relative; background: #ffffff; padding: 2.5rem; border-radius: 24px;
  width: 100%; max-width: 420px; text-align: center;
  box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); border: 1px solid rgba(11, 132, 87, 0.1);
  h3 { margin: 0 0 0.5rem 0; color: #0F172A; font-size: 1.4rem; font-weight: 800; }
  p { color: #64748B; margin-bottom: 0; font-size: 0.95rem; line-height: 1.5; }
`;

const ModalIconWrapper = styled.div`
  width: 55px; height: 55px; background: #FEF2F2; color: #DC2626; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem auto;
`;

const ButtonGroup = styled.div` display: flex; gap: 1rem; justify-content: center; margin-top: 1.8rem; `;

const ModalDangerButton = styled.button`
  flex: 1; padding: 0.9rem 0; border: none; border-radius: 12px; cursor: pointer; background: #EF4444; color: #ffffff; font-weight: 700; font-size: 0.95rem; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2); transition: all 0.2s;
  &:hover { background: #DC2626; box-shadow: 0 6px 16px rgba(239, 68, 68, 0.3); }
`;

const ModalSecondaryButton = styled.button`
  flex: 1; padding: 0.9rem 0; border: 1px solid #E2E8F0; border-radius: 12px; cursor: pointer; background: #ffffff; color: #475569; font-weight: 700; font-size: 0.95rem; transition: all 0.2s;
  &:hover { background: #F8FAFC; color: #0F172A; }
`;