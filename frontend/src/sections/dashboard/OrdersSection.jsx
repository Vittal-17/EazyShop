// src/sections/dashboard/OrdersSection.jsx
import { useState, useContext } from 'react';
import { motion } from 'framer-motion';
import styled from 'styled-components';
import AuthContext from '../../context/AuthContext';
import { FaBoxOpen, FaBox, FaTruck, FaCheckCircle, FaTimesCircle, FaBan, FaStar, FaEdit, FaMapMarkerAlt, FaFileDownload } from 'react-icons/fa';
import { toast } from "react-hot-toast";
import { formatINR } from '../../utils/currency';

const OrdersSection = ({ orders, isLoadingOrders, orderPage, totalOrderPages, setOrderPage, userReviews, openReviewModal, onCancelOrderClick }) => {
  const { axiosInstance } = useContext(AuthContext);
  const [expandedOrderId, setExpandedOrderId] = useState(null);
  const [orderItems, setOrderItems] = useState({});
  const [loadingItems, setLoadingItems] = useState(false);
  const [downloadingOrderId, setDownloadingOrderId] = useState(null);

  const fetchOrderItems = async (orderId) => {
    if (orderItems[orderId]) return;
    setLoadingItems(true);
    try {
      const res = await axiosInstance.get(`/api/order-items/?order=${orderId}`);
      const items = res.data.results || res.data;
      
      const formattedItems = items.map(item => {
        let rawImg = item.image_url || '';
        if (rawImg && rawImg.startsWith('/')) {
          rawImg = `http://127.0.0.1:8000${rawImg}`;
        }
        return { ...item, image_url: rawImg };
      });

      setOrderItems(prev => ({ ...prev, [orderId]: formattedItems }));
    } catch (error) { 
      toast.error('❌ Failed to load order items'); 
    } finally { 
      setLoadingItems(false); 
    }
  };

  // 📄 Handle Invoice PDF Download
  const handleDownloadInvoice = async (orderId) => {
    setDownloadingOrderId(orderId);
    const toastId = toast.loading('📄 Generating secure invoice PDF...');
    try {
      const response = await axiosInstance.get(`/api/orders/${orderId}/invoice/`, {
        responseType: 'blob', // Crucial for handling binary PDF stream
      });
      
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const link = document.createElement('a');
      link.href = window.URL.createObjectURL(blob);
      link.download = `Invoice_INV-${String(orderId).padStart(5, '0')}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      toast.success('📄 Invoice downloaded successfully!', { id: toastId });
    } catch (err) {
      toast.error('❌ Failed to download invoice PDF.', { id: toastId });
    } finally {
      setDownloadingOrderId(null);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'pending': return <StatusBadge $status="pending"><FaBoxOpen /> <span>Pending</span></StatusBadge>;
      case 'shipped': return <StatusBadge $status="shipped"><FaTruck /> <span>Shipped</span></StatusBadge>;
      case 'delivered': return <StatusBadge $status="delivered"><FaCheckCircle /> <span>Delivered</span></StatusBadge>;
      case 'cancelled': return <StatusBadge $status="cancelled"><FaTimesCircle /> <span>Cancelled</span></StatusBadge>;
      default: return <StatusBadge $status="default"><FaBox /> <span>{status}</span></StatusBadge>;
    }
  };

  if (isLoadingOrders) {
    return <LoadingWrapper><Spinner /><LoadingText>Loading your orders...</LoadingText></LoadingWrapper>;
  }

  if (orders.length === 0) {
    return (
      <EmptyState initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
        <span className="emoji">📦</span>
        <h3>No orders found</h3>
        <p>You haven't placed any orders yet.</p>
      </EmptyState>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <OrdersList>
        {orders.map((order) => (
          <OrderCard key={order.id} whileHover={{ y: -2 }} transition={{ duration: 0.2 }}>
            <OrderHeader>
              <div>
                <h3>Order #{order.id}</h3>
                <OrderDate>{new Date(order.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</OrderDate>
              </div>
              {getStatusBadge(order.status)}
            </OrderHeader>
            
            {order.shipping_address && (
              <AddressRow>
                <FaMapMarkerAlt className="icon" /> 
                <span><strong>Shipped To:</strong> {order.shipping_address}</span>
              </AddressRow>
            )}
            
            <OrderFooterRow>
              <OrderTotal>Total: <span>{formatINR(order.total_price)}</span></OrderTotal>
              
              <ActionGroup>
                {/* 📄 Invoice Download Button */}
                <InvoiceButton 
                  onClick={() => handleDownloadInvoice(order.id)}
                  disabled={downloadingOrderId === order.id}
                  whileTap={{ scale: 0.97 }}
                >
                  <FaFileDownload /> {downloadingOrderId === order.id ? 'Generating...' : 'Invoice PDF'}
                </InvoiceButton>

                <ViewItemsButton 
                  onClick={() => { if(expandedOrderId === order.id) setExpandedOrderId(null); else { setExpandedOrderId(order.id); fetchOrderItems(order.id); } }}
                  whileTap={{ scale: 0.97 }}
                >
                  {expandedOrderId === order.id ? 'Hide Items' : 'View Items'}
                </ViewItemsButton>

                {order.status === 'pending' && ( 
                  <DashboardCancelButton onClick={() => onCancelOrderClick(order.id)} whileTap={{ scale: 0.97 }}>
                    <FaBan /> Cancel Order
                  </DashboardCancelButton>
                )}
              </ActionGroup>
            </OrderFooterRow>

            {expandedOrderId === order.id && (
              <ItemsList>
                {loadingItems ? (
                  <LoadingWrapper style={{ margin: '1rem 0' }}><Spinner style={{ width: '30px', height: '30px' }} /></LoadingWrapper>
                ) : (
                  orderItems[order.id]?.map(item => {
                    const existingReview = userReviews.find(r => r.product === item.product);
                    return (
                      <Item key={item.id}>
                        <ItemImage>
                          {item.image_url ? <img src={item.image_url} alt={item.name} /> : <FaBoxOpen size={24} color="#94A3B8" />}
                        </ItemImage>
                        <ItemDetails>
                          <h4>{item.name}</h4>
                          <div className="meta"><span>Qty: {item.quantity}</span><span>{formatINR(item.price)} each</span></div>
                        </ItemDetails>
                        {order.status === 'delivered' && (
                           <ReviewTriggerButton $isEdit={!!existingReview} onClick={() => openReviewModal(item, existingReview)} whileTap={{ scale: 0.97 }}>
                             {existingReview ? <><FaEdit /> Edit Review</> : <><FaStar /> Leave Review</>}
                           </ReviewTriggerButton>
                        )}
                      </Item>
                    );
                  })
                )}
              </ItemsList>
            )}
          </OrderCard>
        ))}
      </OrdersList>

      {totalOrderPages > 1 && (
        <PaginationWrapper>
          <PageButton onClick={() => setOrderPage(p => Math.max(p - 1, 1))} disabled={orderPage === 1}>&larr; Prev</PageButton>
          <PageInfo>Page {orderPage} of {totalOrderPages}</PageInfo>
          <PageButton onClick={() => setOrderPage(p => Math.min(p + 1, totalOrderPages))} disabled={orderPage === totalOrderPages}>Next &rarr;</PageButton>
        </PaginationWrapper>
      )}
    </motion.div>
  );
};

export default OrdersSection;

// ==========================================
// SAAS LEVEL STYLED COMPONENTS
// ==========================================

const LoadingWrapper = styled.div` display: flex; flex-direction: column; align-items: center; justify-content: center; margin-top: 4rem; `;
const Spinner = styled.div` width: 45px; height: 45px; border: 4px solid #E2E8F0; border-top: 4px solid #0B8457; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem; @keyframes spin { to { transform: rotate(360deg); } } `;
const LoadingText = styled.div` font-size: 1.1rem; font-weight: 600; color: #0B8457; `;

const EmptyState = styled(motion.div)`
  text-align: center; padding: 5rem 2rem; background: #ffffff; border-radius: 24px; border: 1px dashed #CBD5E1;
  .emoji { font-size: 3.5rem; display: block; margin-bottom: 1rem; }
  h3 { color: #0F172A; font-size: 1.5rem; font-weight: 800; margin-bottom: 0.5rem; }
  p { color: #64748B; font-size: 1rem; }
`;

const OrdersList = styled.ul` display: flex; flex-direction: column; gap: 1.5rem; list-style: none; padding: 0; `;
const OrderCard = styled(motion.li)`
  background: #ffffff; border-radius: 24px; padding: 1.8rem; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid rgba(11, 132, 87, 0.08);
`;

const OrderHeader = styled.div`
  display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px; margin-bottom: 1rem;
  h3 { margin: 0 0 0.2rem 0; color: #0F172A; font-size: 1.2rem; font-weight: 800; }
`;

const OrderDate = styled.p` color: #64748B; font-size: 0.9rem; margin: 0; font-weight: 500; `;

const StatusBadge = styled.div`
  display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 1rem; border-radius: 50px; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
  background: ${props => props.$status === 'pending' ? '#FEF3C7' : props.$status === 'delivered' ? '#ECFDF5' : props.$status === 'cancelled' ? '#FEF2F2' : '#EFF6FF'};
  color: ${props => props.$status === 'pending' ? '#B45309' : props.$status === 'delivered' ? '#047857' : props.$status === 'cancelled' ? '#DC2626' : '#1D4ED8'};
  border: 1px solid ${props => props.$status === 'pending' ? 'rgba(245, 158, 11, 0.3)' : props.$status === 'delivered' ? 'rgba(16, 185, 129, 0.3)' : props.$status === 'cancelled' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(59, 130, 246, 0.3)'};
`;

const AddressRow = styled.div`
  display: flex; align-items: center; gap: 0.6rem; font-size: 0.95rem; color: #475569; margin-bottom: 1.2rem; background: #F8FAFC; padding: 0.8rem 1rem; border-radius: 12px; border: 1px solid #F1F5F9;
  .icon { color: #0B8457; flex-shrink: 0; }
  strong { color: #0F172A; }
`;

const OrderFooterRow = styled.div`
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; padding-top: 1rem; border-top: 1px solid #F1F5F9;
`;

const OrderTotal = styled.p`
  font-size: 1.1rem; font-weight: 700; color: #64748B; margin: 0;
  span { color: #0F172A; font-weight: 900; font-size: 1.25rem; }
`;

const ActionGroup = styled.div` display: flex; gap: 0.8rem; flex-wrap: wrap; align-items: center; `;

const InvoiceButton = styled(motion.button)`
  display: flex; align-items: center; gap: 0.5rem;
  background: #ECFDF5; color: #0B8457; border: 1px solid rgba(11, 132, 87, 0.2); 
  padding: 0.6rem 1.2rem; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 0.9rem; 
  transition: all 0.2s;
  &:hover:not(:disabled) { background: #D1FAE5; }
  &:disabled { opacity: 0.6; cursor: not-allowed; }
`;

const ViewItemsButton = styled(motion.button)`
  background: #F1F5F9; color: #334155; border: 1px solid #E2E8F0; padding: 0.6rem 1.2rem; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 0.9rem; transition: background 0.2s;
  &:hover { background: #E2E8F0; color: #0F172A; }
`;

const DashboardCancelButton = styled(motion.button)`
  display: flex; align-items: center; gap: 0.5rem; padding: 0.6rem 1.2rem; background-color: #FEF2F2; color: #DC2626; border: 1px solid #FCA5A5; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 0.9rem; transition: background 0.2s;
  &:hover { background-color: #FEE2E2; }
`;

const ItemsList = styled.ul`
  list-style: none; padding: 0; margin-top: 1.5rem; border-top: 1px dashed #E2E8F0; padding-top: 1.2rem; display: flex; flex-direction: column; gap: 1rem;
`;

const Item = styled.li`
  display: flex; align-items: center; gap: 1.2rem; background: #F8FAFC; border-radius: 16px; padding: 1rem; border: 1px solid #F1F5F9; flex-wrap: wrap;
`;

const ItemImage = styled.div`
  width: 60px; height: 60px; background: #ffffff; border-radius: 12px; overflow: hidden; display: flex; align-items: center; justify-content: center; border: 1px solid #E2E8F0; flex-shrink: 0;
  img { width: 100%; height: 100%; object-fit: contain; mix-blend-mode: multiply; }
`;

const ItemDetails = styled.div`
  flex: 1; min-width: 200px;
  h4 { margin: 0 0 0.3rem 0; color: #0F172A; font-weight: 700; font-size: 1.05rem; } 
  .meta { display: flex; gap: 1rem; font-size: 0.9rem; color: #64748B; font-weight: 500; } 
`;

const ReviewTriggerButton = styled(motion.button)`
  display: flex; align-items: center; gap: 0.5rem; padding: 0.6rem 1.2rem; 
  background-color: ${props => props.$isEdit ? '#FEF3C7' : '#ECFDF5'}; 
  color: ${props => props.$isEdit ? '#B45309' : '#047857'}; 
  border: 1px solid ${props => props.$isEdit ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)'}; 
  border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 0.9rem; transition: all 0.2s ease; 
  &:hover { filter: brightness(0.95); } 
  @media (max-width: 600px) { width: 100%; justify-content: center; margin-top: 10px; }
`;

const PaginationWrapper = styled.div` display: flex; justify-content: center; align-items: center; gap: 1rem; margin-top: 3rem; padding-bottom: 1rem; `;
const PageButton = styled.button` padding: 0.6rem 1.4rem; border-radius: 50px; border: none; font-weight: 700; background: ${props => props.disabled ? '#F1F5F9' : '#0B8457'}; color: ${props => props.disabled ? '#94A3B8' : 'white'}; cursor: ${props => props.disabled ? 'not-allowed' : 'pointer'}; transition: 0.2s; box-shadow: ${props => props.disabled ? 'none' : '0 4px 10px rgba(11, 132, 87, 0.2)'}; &:hover:not(:disabled) { background: #086341; transform: translateY(-1px); } `;
const PageInfo = styled.span` font-weight: 700; color: #334155; font-size: 0.95rem; background: #ffffff; padding: 0.6rem 1.2rem; border-radius: 50px; border: 1px solid #E2E8F0; `;