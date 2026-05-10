"use client";

import { Suspense } from "react";
import WidgetContent from "@/components/WidgetContent";

export default function WidgetPage() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <WidgetContent />
        </Suspense>
    );
}
