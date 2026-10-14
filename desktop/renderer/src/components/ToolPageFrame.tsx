import type { ReactNode } from 'react';
import { Button } from 'antd';
import { ArrowLeft } from 'lucide-react';

import { useT } from '../i18n';
import { Banner, PageHeader } from '../ui';

/**
 * 工具详情页外框：对齐 Qt5 工具箱子页层次。
 * 外边距/底色由 .rb-tool-page 负责；.rb-tool-panel 承接余高；
 * 子页根节点（.rb-page-scroll 或 .rb-page）负责内部滚动与 4px 阴影边距。
 */
export function ToolPageFrame(props: {
  title: string;
  description: string;
  blocked: boolean;
  onBack: () => void;
  onOpenProject: () => void;
  children: ReactNode;
}) {
  const { title, description, blocked, onBack, onOpenProject, children } = props;
  const t = useT();
  return (
    <div className="rb-page rb-tool-page" data-rb-tool-frame="">
      <PageHeader
        title={title}
        description={description}
        actions={<Button type="default" icon={<ArrowLeft size={16} />} onClick={onBack}>{t('app_back_to_toolbox')}</Button>}
      />
      {blocked ? (
        <Banner tone="warning">
          <div className="rb-tool-blocked">
            <span>{t('app_tool_needs_project')}</span>
            <Button type="default" onClick={onOpenProject}>{t('app_go_project_settings')}</Button>
          </div>
        </Banner>
      ) : (
        <div className="rb-tool-panel">{children}</div>
      )}
    </div>
  );
}
