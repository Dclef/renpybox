import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from 'antd';

import { useT } from '../i18n';

type BoundaryProps = {
  title: string;
  hint: string;
  retry: string;
  detail: string;
  children: ReactNode;
  onRetry?: () => void;
};

type BoundaryState = { message: string };

/**
 * 页面渲染异常的兜底。
 * React 19 在渲染期抛错时会卸载整棵树：没有边界时任何一页的意外错误都会
 * 让整个窗口变成无提示的空白页（侧栏也一起消失，未保存的稿子全丢）。
 */
class Boundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { message: '' };

  static getDerivedStateFromError(error: unknown): BoundaryState {
    return { message: error instanceof Error ? error.message : String(error) };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // 保留一份带组件栈的控制台记录，方便自检脚本与用户日志定位。
    console.error('[renderer] 渲染异常已被 ErrorBoundary 拦截：', error, info.componentStack);
  }

  private reset = () => {
    this.setState({ message: '' });
    this.props.onRetry?.();
  };

  render() {
    if (!this.state.message) return this.props.children;
    return (
      <div className="rb-page rb-page-scroll" data-rb-error-boundary="">
        <div className="rb-error-boundary" role="alert">
          <h1>{this.props.title}</h1>
          <p>{this.props.hint}</p>
          <details className="rb-error-boundary-more">
            <summary>{this.props.detail}</summary>
            <pre className="rb-error-boundary-detail">{this.state.message}</pre>
          </details>
          <Button type="primary" onClick={this.reset}>{this.props.retry}</Button>
        </div>
      </div>
    );
  }
}

/** 带文案的边界；onRetry 用于让上层重挂出错的页面（重新取数）。 */
export function ErrorBoundary({ children, onRetry }: { children: ReactNode; onRetry?: () => void }) {
  const t = useT();
  return (
    <Boundary
      title={t('error_boundary_title')}
      hint={t('error_boundary_hint')}
      retry={t('error_boundary_retry')}
      detail={t('error_boundary_detail')}
      onRetry={onRetry}
    >
      {children}
    </Boundary>
  );
}
