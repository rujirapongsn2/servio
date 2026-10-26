"use client";

import { Suspense } from "react";
import WidgetContent from "@/components/WidgetContent";

export default function WidgetPage() {
    return (
        <div className="w-full h-dvh min-h-0 overflow-hidden"><Suspense fallback={<div role="status">กำลังโหลด…</div>}>
            <WidgetContent />
        </Suspense></div>
    );
}
