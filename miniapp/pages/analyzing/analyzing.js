// pages/analyzing/analyzing.js — AI 分析进度页
const app = getApp();
const { request } = require('../../utils/request');

Page({
  data: {
    currentStep: 0,        // 0-3: upload, exif, ai, diary
    steps: [
      { title: '读取照片信息', desc: '解析 EXIF 时间和 GPS', status: 'pending', isDone: false, isActive: false },
      { title: 'AI 图片分析', desc: '识别场景、活动、氛围', status: 'pending', isDone: false, isActive: false },
      { title: '生成游玩日志', desc: '整理照片并生成日记', status: 'pending', isDone: false, isActive: false },
    ],
    isAnalyzing: false,
    isDone: false,
    diaryId: null,
    errorMessage: '',
    hasError: false,
    showNormalArea: true,
    showSpinner: true,
    analyzingTitle: '正在分析照片...',
  },

  onLoad() {
    this.startAnalysis();
  },

  async startAnalysis() {
    const photoIds = app.globalData.uploadedPhotoIds;
    if (!photoIds || photoIds.length === 0) {
      wx.showToast({ title: '没有需要分析的照片', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1500);
      return;
    }

    this.setAnalysisData({
      isAnalyzing: true,
      currentStep: 0,
      isDone: false,
      errorMessage: '',
      hasError: false,
      showNormalArea: true,
    });
    this.updateStep(0, 'active');

    try {
      // ---- Step 1: EXIF 已在后端 upload 时读取，这里主要是 AI 分析 ----
      this.updateStep(0, 'done');
      this.updateStep(1, 'active');
      this.setAnalysisData({ currentStep: 1 });

      // 调用分析接口
      const analyzeResult = await request('/analyze', 'POST', {
        photo_ids: photoIds,
        geocode: true,
      });

      const analyzeErrors = analyzeResult.errors || [];
      const resultErrors = (analyzeResult.results || []).filter(item => item.error);
      if (!analyzeResult.success || analyzeErrors.length > 0 || resultErrors.length > 0) {
        const firstAnalyzeError = analyzeErrors.length > 0 ? analyzeErrors[0].error : '';
        const firstResultError = resultErrors.length > 0 ? resultErrors[0].error : '';
        throw new Error(firstAnalyzeError || firstResultError || 'AI 图片识别失败');
      }

      this.updateStep(1, 'done');
      this.updateStep(2, 'active');
      this.setAnalysisData({ currentStep: 2 });

      // ---- Step 2: 生成游玩日志 ----
      const diaryResult = await request('/diary/generate', 'POST', {
        photo_ids: photoIds,
      });

      this.updateStep(2, 'done');
      this.setAnalysisData({ currentStep: 3, isDone: true, diaryId: diaryResult.diary_id });

      // 保存结果
      app.globalData.currentDiary = diaryResult;

      // 跳转到结果页
      setTimeout(() => {
        wx.redirectTo({ url: '/pages/result/result' });
      }, 800);

    } catch (err) {
      console.error('分析失败:', err);
      this.setAnalysisData({
        isAnalyzing: false,
        errorMessage: err.message || '分析失败，请检查后端是否正常运行',
        hasError: true,
        showNormalArea: false,
      });
    }
  },

  setAnalysisData(changes) {
    const nextData = Object.assign({}, this.data, changes);
    const derived = {
      hasError: !!nextData.errorMessage,
      showNormalArea: !nextData.errorMessage,
      showSpinner: !nextData.isDone,
      analyzingTitle: nextData.isDone ? '分析完成!' : '正在分析照片...',
    };
    this.setData(Object.assign({}, changes, derived));
  },

  updateStep(index, status) {
    const steps = this.data.steps.map(step => Object.assign({}, step));
    steps[index].status = status;
    steps[index].isDone = status === 'done';
    steps[index].isActive = status === 'active';
    this.setData({ steps });
  },

  goBack() {
    wx.navigateBack();
  },

  retry() {
    this.setAnalysisData({ errorMessage: '', currentStep: 0 });
    this.startAnalysis();
  },
});
