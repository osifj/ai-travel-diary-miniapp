// ==========================================
// AI 游玩日志生成系统 — 微信小程序入口
// ==========================================

App({
  globalData: {
    // 后端 API 地址
    // 模拟器本机: http://127.0.0.1:8000
    // 真机调试: 使用电脑局域网 IP，后端需监听 0.0.0.0
    baseUrl: 'http://192.168.8.158:8000',

    // 已上传的照片 ID 列表 (本次会话)
    uploadedPhotoIds: [],

    // 当前生成的日志
    currentDiary: null,
  },

  onLaunch() {
    console.log('AI 游玩日志生成器 启动');
    
    // 检查后端连通性
    this.checkBackendHealth();
  },

  checkBackendHealth() {
    const that = this;
    wx.request({
      url: `${that.globalData.baseUrl}/health`,
      method: 'GET',
      success(res) {
        if (res.statusCode === 200 && res.data.status === 'ok') {
          console.log('✅ 后端连接正常');
        } else {
          console.warn('⚠️ 后端状态异常:', res.data);
        }
      },
      fail(err) {
        console.error('❌ 无法连接后端:', err.errMsg);
        console.warn('请确认: 1) 后端已启动 2) 地址配置正确 3) 微信开发者工具已勾选"不校验合法域名"');
      }
    });
  }
});
