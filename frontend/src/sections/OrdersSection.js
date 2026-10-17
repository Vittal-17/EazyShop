// src/sections/OrdersSection.jsx
import { useState, useEffect, useContext } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import AuthContext from '../context/AuthContext';
import { toast } from "react-hot-toast";
import { FaTimes, FaClock, FaShippingFast, FaCheckCircle, FaTimesCircle, FaEdit } from 'react-icons/fa';
import ModalPortal from '../components/ModalPortal';
import { formatINR } from '../utils/currency';

const OrdersSection = () => {
  const { axiosInstance } = useContext(AuthContext);
  const [orders, setOrders] = useState([]);
  const [products, setProducts] = useState([]);
  const [activeOrder, setActiveOrder] = useState(null);
  
  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const fetchOrdersAndProducts = async () => {
    try {
      const [ordersRes, usersRes, productsRes] = await Promise.all([
        axiosInstance.get(`/api/orders/admin-all/?page=${currentPage}`), 
        axiosInstance.get('/api/users/?page_size=1000'),
        axiosInstance.get('/api/products/?page_size=1000') 
      ]);

      const fetchedOrders = ordersRes.data.results || ordersRes.data;
      const fetchedUsers = usersRes.data.results || usersRes.data;
      
      setProducts(productsRes.data.results || productsRes.data);

      if (ordersRes.data.count) {
        setTotalPages(Math.ceil(ordersRes.data.count / 12));
      }

      const ordersWithUsers = fetchedOrders.map(o => ({
        ...o,
        username: fetchedUsers.find(u => u.id === o.user)?.username || 'Unknown'
      }));

      setOrders(ordersWithUsers.sort((a, b) => b.id - a.id));
    } catch {
      toast.error('❌ Failed to fetch order data');
    }
  };

  useEffect(() => {
    fetchOrdersAndProducts();
    // eslint-disable-next-line
  }, [currentPage]); 

  const handleStatusChange = async (orderId, newStatus) => {
    if (newStatus === 'cancelled' && !window.confirm('Cancel this order? This will restore the items to the inventory.')) return;
    try {
      await axiosInstance.patch(`/api/orders/${orderId}/`, { status: newStatus });
      toast.success(`✅ Order #${orderId} marked as ${newStatus.toUpperCase()}`);
      setActiveOrder(null); 
      fetchOrdersAndProducts();
    } catch { toast.error('❌ Failed to update order status'); }
  };

  const getStatusConfig = (status) => {
    switch (status) {
      case 'pending': return { bg: '#FEF3C7', fg: '#B45309', border: '#F59E0B', icon: <FaClock />, label: 'Pending' };
      case 'shipped': return { bg: '#DBEAFE', fg: '#1D4ED8', border: '#3B82F6', icon: <FaShippingFast />, label: 'Shipped' };
      case 'delivered': return { bg: '#ECFDF5', fg: '#047857', border: '#10B981', icon: <FaCheckCircle />, label: 'Delivered' };
      case 'cancelled': return { bg: '#FEF2F2', fg: '#B91C1C', border: '#EF4444', icon: <FaTimesCircle />, label: 'Cancelled' };
      default: return { bg: '#F1F5F9', fg: '#334155', border: '#94A3B8', icon: <FaClock />, label: 'Unknown' };
    }
  };

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <SectionTitle>📋 Manage Orders</SectionTitle>
      
      <ul style={{ padding: 0, listStyle: 'none' }}>
        {orders.map(o => {
          const config = getStatusConfig(o.status);
          const isLocked = o.status === 'cancelled' || o.status === 'delivered';

          return (
            <ListItem key={o.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} whileHover={{ y: -2 }}>
              <OrderDetails>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
                  <div>
                    <div style={{ fontSize: '1.15rem', fontWeight: '800', color: '#0F172A' }}>Order #{o.id}</div>
                    <div style={{ color: '#64748B', marginTop: '0.3rem', fontSize: '0.95rem' }}>Customer: <strong style={{ color: '#0F172A' }}>{o.username}</strong></div>
                    <div style={{ color: '#0B8457', fontWeight: '900', marginTop: '0.4rem', fontSize: '1.2rem' }}>Total: {formatINR(o.total_price)}</div>
                  </div>
                  <StatusTriggerButton 
                    $bg={config.bg} $fg={config.fg} onClick={() => setActiveOrder(o)}
                    disabled={isLocked} whileHover={!isLocked ? { scale: 1.02 } : {}} whileTap={!isLocked ? { scale: 0.98 } : {}}
                  >
                    {config.icon} {config.label} {!isLocked && <FaEdit style={{ marginLeft: '4px', fontSize: '0.8rem' }}/>}
                  </StatusTriggerButton>
                </div>
                <ItemsContainer>
                  {o.order_items?.map((item, index) => {
                    const productInfo = products.find(p => p.id === item.product);
                    return (
                      <ProductRow key={index}>
                        <ProductImage>{productInfo?.image_url ? <img src={productInfo.image_url} alt={productInfo.name} /> : <span>No Img</span>}</ProductImage>
                        <ProductInfo><span className="name">{productInfo?.name || `Product #${item.product}`}</span><span className="details">Qty: {item.quantity} | ${Number(item.price).toFixed(2)} each</span></ProductInfo>
                      </ProductRow>
                    );
                  })}
                </ItemsContainer>
              </OrderDetails>
            </ListItem>
          );
        })}
      </ul>

      {totalPages > 1 && (
        <PaginationWrapper>
          <PageButton onClick={() => setCurrentPage(p => Math.max(p - 1, 1))} disabled={currentPage === 1}>&larr; Prev</PageButton>
          <PageInfo>Page {currentPage} of {totalPages}</PageInfo>
          <PageButton onClick={() => setCurrentPage(p => Math.min(p + 1, totalPages))} disabled={currentPage === totalPages}>Next &rarr;</PageButton>
        </PaginationWrapper>
      )}

      {/* Modals */}
      <AnimatePresence>
        {activeOrder && (
          <ModalPortal>
          <ModalOverlay initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setActiveOrder(null)}>
            <ModalCard initial={{ scale: 0.9, opacity: 0, y: 10 }} animate={{ scale: 1, opacity: 1, y: 0 }} exit={{ scale: 0.9, opacity: 0, y: 10 }} onClick={e => e.stopPropagation()}>
              <CloseButton onClick={() => setActiveOrder(null)}><FaTimes /></CloseButton>
              <ModalTitle>Update Order #{activeOrder.id}</ModalTitle>
              <StatusOptionList>
                {['pending', 'shipped', 'delivered', 'cancelled'].map(statusType => {
                  const optConfig = getStatusConfig(statusType);
                  const isActive = activeOrder.status === statusType;
                  return (
                    <StatusOptionBtn key={statusType} $bg={optConfig.bg} $fg={optConfig.fg} $borderColor={optConfig.border} $active={isActive} onClick={() => !isActive && handleStatusChange(activeOrder.id, statusType)} whileHover={!isActive ? { scale: 1.02 } : {}}>
                      {optConfig.icon} <span style={{ flex: 1, textAlign: 'left' }}>{optConfig.label}</span> {isActive && <span style={{ fontSize: '0.8rem', opacity: 0.7 }}>(Current)</span>}
                    </StatusOptionBtn>
                  );
                })}
              </StatusOptionList>
            </ModalCard>
          </ModalOverlay>
          </ModalPortal>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default OrdersSection;

// STYLED COMPONENTS
const SectionTitle = styled.h2` color: #0F172A; margin-bottom: 1.5rem; font-size: 1.5rem; font-weight: 800; `;
const ListItem = styled(motion.li)` background: #ffffff; padding: 1.8rem; border-radius: 20px; margin-bottom: 1rem; display: flex; flex-direction: column; gap: 1.5rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08); `;
const OrderDetails = styled.div` flex: 1; width: 100%; `;
const StatusTriggerButton = styled(motion.button)` display: flex; align-items: center; gap: 0.5rem; padding: 0.6rem 1.2rem; border-radius: 12px; font-weight: 700; text-transform: uppercase; border: 1px solid ${props => props.$border || 'transparent'}; cursor: pointer; background-color: ${props => props.$bg}; color: ${props => props.$fg}; min-width: 150px; justify-content: center; font-size: 0.9rem; &:hover:not(:disabled) { filter: brightness(0.95); } &:disabled { cursor: not-allowed; opacity: 0.7; } `;
const ItemsContainer = styled.div` margin-top: 1.5rem; padding-top: 1.5rem; border-top: 1px dashed #E2E8F0; display: flex; flex-direction: column; gap: 1rem; `;
const ProductRow = styled.div` display: flex; align-items: center; gap: 1rem; background: #F8FAFC; padding: 0.8rem; border-radius: 12px; border: 1px solid #F1F5F9; `;
const ProductImage = styled.div` width: 60px; height: 60px; background: white; border-radius: 10px; padding: 4px; border: 1px solid #E2E8F0; display: flex; align-items: center; justify-content: center; img { max-width: 100%; max-height: 100%; object-fit: contain; mix-blend-mode: multiply; } span { font-size: 0.7rem; color: #94A3B8; } `;
const ProductInfo = styled.div` display: flex; flex-direction: column; gap: 0.2rem; .name { font-weight: 700; color: #0F172A; } .details { font-size: 0.9rem; color: #64748B; font-weight: 500; } `;

const PaginationWrapper = styled.div` display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 3rem; padding-bottom: 1rem; `;
const PageButton = styled.button` padding: 0.6rem 1.4rem; border-radius: 50px; border: none; font-weight: 700; background: ${props => props.disabled ? '#F1F5F9' : '#0B8457'}; color: ${props => props.disabled ? '#94A3B8' : 'white'}; cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'}; transition: 0.2s; box-shadow: ${props => props.disabled ? 'none' : '0 4px 10px rgba(11, 132, 87, 0.2)'}; &:hover:not(:disabled) { background: #086341; transform: translateY(-1px); } `;
const PageInfo = styled.span` font-weight: 700; color: #334155; font-size: 0.95rem; background: #ffffff; padding: 0.6rem 1.2rem; border-radius: 50px; border: 1px solid #E2E8F0; `;

const ModalOverlay = styled(motion.div)` position: fixed; inset: 0; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 1rem; `;
const ModalCard = styled(motion.div)` background: white; width: 100%; max-width: 420px; border-radius: 24px; padding: 2.5rem; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); position: relative; border: 1px solid rgba(11, 132, 87, 0.1); `;
const CloseButton = styled.button` position: absolute; top: 1.5rem; right: 1.5rem; background: none; border: none; font-size: 1.2rem; color: #94A3B8; cursor: pointer; &:hover { color: #0F172A; } `;
const ModalTitle = styled.h3` margin: 0 0 1.5rem 0; color: #0F172A; text-align: center; font-size: 1.4rem; font-weight: 800; `;
const StatusOptionList = styled.div` display: flex; flex-direction: column; gap: 0.8rem; `;
const StatusOptionBtn = styled(motion.button)` display: flex; align-items: center; gap: 1rem; width: 100%; padding: 1rem 1.2rem; border: 2px solid ${props => props.$active ? props.$borderColor : 'transparent'}; border-radius: 14px; background-color: ${props => props.$bg}; color: ${props => props.$fg}; font-size: 1.05rem; font-weight: 700; cursor: pointer; &:hover { filter: brightness(0.95); } `;